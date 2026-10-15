# ruff: noqa: S101, PT018, PLR2004 - Standalone acceptance checks intentionally assert invariants.
"""Exercise real HTTP publication, version pinning and permanent Job deduplication on synthetic data.

Requires run_local platform/api/demo and the isolated PostgreSQL service. Run with no competing
Worker: this script drives the same run_once function and leaves its two-version rule for inspection.
"""

import asyncio
import copy
import json
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from langflow.verification.database import Database
from langflow.verification.demo import example_task
from langflow.verification.settings import VerificationSettings
from langflow.verification.worker import run_once

ROOT = Path(__file__).resolve().parents[2]


async def main():
    private = dotenv_values(ROOT / "deploy/verification/.env")
    api_port = int(private.get("VERIFICATION_SOURCE_API_PORT") or "8081")
    settings = VerificationSettings(
        internal_token=private["VERIFICATION_INTERNAL_TOKEN"],
        database_url="postgresql+psycopg://verification_app:"
        + quote(private["VERIFICATION_DB_PASSWORD"], safe="")
        + "@127.0.0.1:55433/verification",
        database_schema="verification_scope",
        clients=json.loads(private["VERIFICATION_CLIENTS"]),
        langflow_url="http://127.0.0.1:7860",
        langflow_api_key=private["VERIFICATION_LANGFLOW_API_KEY"],
        api_url=f"http://127.0.0.1:{api_port}",
        demo_mode=True,
    )
    database = Database(settings.database_url.get_secret_value(), settings.database_schema)
    code = "scope_acceptance_" + uuid4().hex[:8]
    exported = json.loads((ROOT / "deploy/verification/consumable-verification-palette.json").read_text())
    exported["name"] = code
    exported.pop("endpoint_name", None)
    for n in exported["data"]["nodes"]:
        if n["id"].endswith("-01"):
            n["data"]["node"]["template"]["page_size"]["value"] = 1
    output = ROOT / "deploy/verification/.cache/scope-release-acceptance" / code
    output.mkdir(parents=True)
    async with (
        httpx.AsyncClient(base_url=settings.langflow_url, timeout=90) as platform,
        httpx.AsyncClient(
            base_url=settings.api_url,
            headers={"Authorization": "Bearer " + json.loads(private["VERIFICATION_CLIENTS"])["demo-regulator"]},
            timeout=30,
        ) as api,
        httpx.AsyncClient() as worker_http,
    ):
        response = await platform.post(
            "/api/v1/login", data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]}
        )
        response.raise_for_status()
        platform.headers["Authorization"] = "Bearer " + response.json()["access_token"]

        async def platform_call(method, path, **kwargs):
            r = await platform.request(method, path, **kwargs)
            if not r.is_success:
                msg = f"{method} {path}: HTTP {r.status_code} {r.text[:1000]}"
                raise RuntimeError(msg)
            return r.json()

        flow = (
            await platform_call(
                "POST",
                "/api/v1/flows/upload/",
                files={"file": ("scope.json", json.dumps(exported), "application/json")},
            )
        )[0]
        path = "/api/v1/verification/rules/" + code
        await platform_call(
            "POST", "/api/v1/verification/rules", json={"code": code, "name": code, "flow_id": flow["id"]}
        )

        async def publish_activate(revision):
            candidate = await platform_call(
                "POST",
                path + "/candidates",
                json={
                    "catalog_mapping": {"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"},
                    "note": "Real HTTP version isolation acceptance",
                },
            )
            assert candidate["validation"]["simulation"] == "passed"
            release = await platform_call(
                "POST",
                path + "/releases",
                json={"candidate_id": candidate["id"], "content_hash": candidate["content_hash"]},
            )
            await platform_call(
                "PUT", path + "/active", json={"release_id": release["id"], "expected_revision": revision}
            )
            return release

        async def accept(label):
            body = {**example_task(), "rule": code}
            r = await api.post("/api/v1/verification/tasks", json=body, headers={"Idempotency-Key": code + label})
            r.raise_for_status()
            return r.json()

        v1 = await publish_activate(0)
        a = await accept("-a")
        graph_v2 = copy.deepcopy(exported["data"])
        for n in graph_v2["nodes"]:
            if n["id"].endswith("-07"):
                n["data"]["node"]["template"]["comparisons"]["value"] = ["种类"]
        await platform_call("PATCH", "/api/v1/flows/" + flow["id"], json={"data": graph_v2})
        v2 = await publish_activate(1)
        b = await accept("-b")
        assert a["release_id"] == v1["id"] and b["release_id"] == v2["id"]
        saved = []
        for label, accepted in [("a", a), ("b", b)]:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                await run_once(database, settings, worker_http)
                r = await api.get(
                    f"/api/v1/verification/tasks/{accepted['task_id']}/results", params={"run_id": accepted["run_id"]}
                )
                r.raise_for_status()
                result = r.json()
                if result["status"] not in {"waiting", "running"}:
                    break
                await asyncio.sleep(0.5)
            assert result["status"] == "completed", result
            assert len(result["result"]["results"]) == 2
            hip = next(row for row in result["result"]["results"] if row["category"] == "hip_prosthesis")
            assert hip["quantity"]["status"] == ("less" if label == "a" else "equal"), hip
            evidence = (
                await api.get(
                    f"/api/v1/verification/tasks/{accepted['task_id']}/evidence", params={"run_id": accepted["run_id"]}
                )
            ).json()
            saved.append(result)
            (output / f"{label}-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            (output / f"{label}-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            duplicate = await accept("-" + label)
            assert duplicate["run_id"] == accepted["run_id"] and duplicate["job_id"] == accepted["job_id"]
            # Repeat execution after the business receipt and original Job completion.
            worker_headers = {"x-api-key": private["VERIFICATION_LANGFLOW_API_KEY"]}
            for _ in range(60):
                job = await platform_call(
                    "GET", f"/api/v1/verification/runs/{accepted['run_id']}/job", headers=worker_headers
                )
                if job["status"] == "completed":
                    break
                await asyncio.sleep(0.2)
            assert job["status"] == "completed", job
            for _ in range(2):
                repeated = await platform_call(
                    "POST", f"/api/v1/verification/runs/{accepted['run_id']}/execute", headers=worker_headers
                )
                assert repeated["job_id"] == accepted["job_id"] and repeated["status"] == "completed"
        summary = {
            "rule": code,
            "flow_id": flow["id"],
            "v1": v1,
            "v2": v2,
            "runs": [
                {k: r[k] for k in ["task_id", "run_id", "job_id", "release_id", "status", "progress"]} for r in saved
            ],
            "version_isolation": "passed",
            "terminal_job_deduplication": "passed",
        }
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("Evidence:", output)
    database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
