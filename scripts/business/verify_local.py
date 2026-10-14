"""Verify the running project's Worker, public results, source isolation and retained history."""

import json
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import text

from langflow.verification.database import Database

ROOT = Path(__file__).resolve().parents[2]


def get(http, path):
    response = http.get(path)
    response.raise_for_status()
    return response.json()


def main():
    private = dotenv_values(ROOT / "deploy/verification/.env")
    clients = json.loads(private["VERIFICATION_CLIENTS"])
    source, token = next(iter(clients.items()))
    report = {"source": source, "tasks": {}}
    port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, timeout=60
    ) as public:
        catalog = {item["code"]: item for item in get(public, "/api/v1/business/schemes")}
        for code, expected in [
            ("demo.cross_database.v2", {"equal", "different", "left_only", "right_only"}),
            ("demo.consumables.v2", {"equal", "different"}),
        ]:
            assert code in catalog
            response = public.post(
                "/api/v1/business/tasks",
                headers={"Idempotency-Key": f"local-acceptance-{uuid4()}"},
                json={"scheme": code, "parameters": {}},
            )
            response.raise_for_status()
            task_id = response.json()["id"]
            for _ in range(120):
                task = get(public, f"/api/v1/business/tasks/{task_id}")
                if task["status"] not in {"waiting", "running"}:
                    break
                time.sleep(1)
            assert task["status"] == "completed", task.get("error")
            primary = next(d for d in task["datasets"] if d["node_id"] == "Results" and d["port"] == "data")
            result = get(public, f"/api/v1/business/tasks/{task_id}/datasets/{primary['id']}?limit=50")
            assert {r["_comparison_status"] for r in result["rows"]} == expected
            assert task["assessment"]["state"] == "accounted", task["assessment"]
            if code == "demo.cross_database.v2":
                raw = next(d for d in task["datasets"] if d["node_id"] == "Orders" and d["raw"])
                assert "description" in get(public, f"/api/v1/business/tasks/{task_id}/datasets/{raw['id']}")["rows"][0]
            else:
                assert all(r["simulated"] for r in result["rows"])
                assert next(d for d in task["datasets"] if d["node_id"] == "UnknownCategories")["row_count"] == 1
                assert next(d for d in task["datasets"] if d["node_id"] == "UnknownFacts")["row_count"] == 1
            for other_source, other_token in clients.items():
                if other_source == source:
                    continue
                denied = public.get(
                    f"/api/v1/business/tasks/{task_id}/datasets/{task['results'][0]}",
                    headers={"Authorization": "Bearer " + other_token},
                )
                assert denied.status_code == 404
            report["tasks"][code] = {
                "id": task_id,
                "status": task["status"],
                "version": task["version"],
                "result_count": result["total"],
                "unresolved_rows": task["unresolved_rows"],
                "assessment": task["assessment"],
                "url": f"http://localhost:3000/business/tasks/{task_id}",
            }
        closed = public.post(
            "/api/v1/verification/tasks",
            headers={"Idempotency-Key": f"closed-intake-{uuid4()}"},
            json={
                "hospital_scope": "synthetic-hospital",
                "rule": "test",
                "settlement_time_range": {
                    "start_inclusive": "2024-01-01T00:00:00Z",
                    "end_exclusive": "2027-01-01T00:00:00Z",
                },
            },
        )
        assert closed.status_code == 410
        report["legacy_intake_status"] = closed.status_code
    database = Database(
        "postgresql+psycopg://verification_app:"
        + quote(private["VERIFICATION_DB_PASSWORD"], safe="")
        + "@127.0.0.1:55433/verification",
        "verification_scope",
    )
    with database.sessions() as session:
        history = {
            name: session.execute(text("select count(*) from verification_scope." + name)).scalar()
            for name in ["task", "run", "rule_release", "artifact"]
        }
        history["run_statuses"] = [
            dict(row)
            for row in session.execute(
                text("select status,count(*) as count from verification_scope.run group by status")
            ).mappings()
        ]
    database.engine.dispose()
    before_path = ROOT / "deploy/verification/.cache/business-history-before.json"
    if before_path.exists():
        before = json.loads(before_path.read_text())
        for key in ["task", "run", "rule_release", "artifact"]:
            assert history[key] == before[key]
        assert sorted(history["run_statuses"], key=lambda r: r["status"]) == sorted(
            before["run_statuses"], key=lambda r: r["status"]
        )
    report["history"] = history
    path = ROOT / "deploy/verification/.cache/business-local-acceptance.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
