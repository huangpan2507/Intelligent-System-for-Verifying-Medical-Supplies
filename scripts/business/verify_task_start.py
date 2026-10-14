"""Migrate only the core entry, then verify regulator intake through the local Worker."""
# ruff: noqa: S101 - explicit local acceptance assertions.

import argparse
import copy
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from langflow.business.components import to_langflow

ROOT = Path(__file__).resolve().parents[2]
CORE_FLOW = "e55b03b0-7c7f-420b-b720-33b1a4cf5559"
OUTPUT = ROOT / "deploy/business/evidence/task-start-20261013"


def call(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def migrate(http):
    path = f"/api/v1/flows/{CORE_FLOW}"
    flow = call(http, "GET", path)
    original = flow["data"]
    canvas = copy.deepcopy(original)
    entry = next(n for n in canvas["nodes"] if n["id"] == "Request")
    if entry["data"]["type"].endswith("BusinessTaskinput@extra"):
        print("Core flow already uses Task Start")
        return
    assert "BusinessParameters" in entry["data"]["type"]
    config = json.loads(entry["data"]["node"]["template"]["configuration"]["value"])
    assert {p["name"] for p in config["parameters"]} == {"hospital_name", "start", "end"}
    generated = to_langflow({"nodes": [{"id": "Request", "kind": "taskinput", "label": "Task Start"}], "edges": []})
    replacement = generated["nodes"][0]
    entry["data"]["type"] = replacement["data"]["type"]
    entry["data"]["node"] = replacement["data"]["node"]
    for edge in canvas["edges"]:
        if edge["source"] == "Request":
            edge["data"]["sourceHandle"]["dataType"] = replacement["data"]["type"]
            edge["sourceHandle"] = json.dumps(
                edge["data"]["sourceHandle"], sort_keys=True, separators=(",", ":")
            ).replace('"', "œ")
    backup = ROOT / "deploy/verification/.cache/core-before-task-start.json"
    backup.write_text(json.dumps(flow, ensure_ascii=False, indent=2) + "\n")
    # Do not overwrite an edit made while preparing this targeted migration.
    assert call(http, "GET", path)["data"] == original, "Canvas changed; reload before migration"
    call(http, "PATCH", path, json={"data": canvas})
    saved = call(http, "GET", path)["data"]
    assert saved == canvas
    assert [n for n in saved["nodes"] if n["id"] != "Request"] == [n for n in original["nodes"] if n["id"] != "Request"]
    print("Migrated only the core Request node and its source handle type; retained all other nodes")


def verify(http, private):
    clients = json.loads(private["VERIFICATION_CLIENTS"])
    source, token = next(iter(clients.items()))
    graph = {
        "nodes": [
            {"id": "Request", "kind": "taskinput", "label": "Task Start", "position": {"x": 0, "y": 0}},
            {
                "id": "Settlements",
                "kind": "database",
                "position": {"x": 400, "y": 0},
                "config": {
                    "connection": "537d8c03-3c9a-4c25-8a8e-d66cfc2b187a",
                    "schema": "public",
                    "table": "core_flow_settlement_v1",
                    "timezone": "Asia/Shanghai",
                    "conditions": [
                        {"field": "ORGAN_NAME", "op": "eq", "parameter": "hospital_name"},
                        {"field": "UPDATE_TIME", "op": "ge", "parameter": "start"},
                        {"field": "UPDATE_TIME", "op": "le", "parameter": "end"},
                    ],
                },
            },
            {
                "id": "Results",
                "kind": "output",
                "position": {"x": 800, "y": 0},
                "config": {
                    "name": "Task entry acceptance",
                    "columns": ["ORGAN_NAME", "UPDATE_TIME", "SETL_FEE_LIST_ID"],
                },
            },
        ],
        "edges": [
            {"source": a, "target": b, "port": "data", "input": "data"}
            for a, b in [("Request", "Settlements"), ("Settlements", "Results")]
        ],
    }
    code = "acceptance.taskstart." + uuid4().hex[:10]
    scheme = call(
        http,
        "POST",
        "/api/v1/business/schemes",
        json={
            "code": code,
            "name": "监管任务入口验收(模拟)-" + code.rsplit(".", 1)[-1],
            "graph": graph,
            "allowed_sources": [source],
        },
    )
    release = call(
        http, "POST", f"/api/v1/business/schemes/{code}/releases", json={"expected_revision": scheme["revision"]}
    )
    schemes = call(http, "GET", "/api/v1/business/schemes")
    scheme = next(s for s in schemes if s["code"] == code)
    call(
        http,
        "PUT",
        f"/api/v1/business/schemes/{code}/active",
        json={"release_id": release["id"], "expected_revision": scheme["revision"]},
    )
    report = {
        "flow_id": scheme["flow_id"],
        "scheme": code,
        "release_id": release["id"],
        "tasks": [],
        "core_flow_executed": False,
    }
    port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, timeout=30
    ) as public:
        # Two independent requests, with different hospitals and periods. No fixed hospital enum.
        for index, (hospital, start, end, count) in enumerate(
            [
                ("核心流程模拟医院", "2025-08-01 00:00:00", "2025-08-31 23:59:59", 2),
                ("另一家模拟医院", "2025-09-01 00:00:00", "2025-09-30 23:59:59", 0),
            ]
        ):
            body = {
                "scheme": code,
                "external_task_id": f"MOCK-REG-{index + 1}",
                "parameters": {"hospital_name": hospital, "start": start, "end": end},
            }
            headers = {"Idempotency-Key": str(uuid4())}
            task = call(public, "POST", "/api/v1/business/tasks", json=body, headers=headers)
            assert call(public, "POST", "/api/v1/business/tasks", json=body, headers=headers)["id"] == task["id"]
            report["tasks"].append({"id": task["id"], "expected_count": count, "input": task["task_input"]})
        for entry in report["tasks"]:
            for _ in range(180):
                task = call(public, "GET", f"/api/v1/business/tasks/{entry['id']}")
                if task["status"] not in {"waiting", "running"}:
                    break
                time.sleep(1)
            assert task["status"] == "completed", task.get("error")
            assert task["progress"]["Request"]["outputs"]["data"] == entry["input"]
            result = call(public, "GET", f"/api/v1/business/tasks/{entry['id']}/datasets/{task['results'][0]}")
            assert result["total"] == entry["expected_count"]
            entry.update(status=task["status"], row_count=result["total"], job_id=task["job_id"])
    report["worker_executed"] = True
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate-core", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
        login = call(
            http,
            "POST",
            "/api/v1/login",
            data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
        )
        http.headers["Authorization"] = "Bearer " + login["access_token"]
        if args.migrate_core:
            migrate(http)
        if args.verify:
            verify(http, private)
    if args.browser:
        browser_config = {
            "testDir": str(ROOT / "src/frontend/tests"),
            "testMatch": "core/features/business-task-start.spec.ts",
            "timeout": 240000,
            "workers": 1,
            "retries": 0,
            "reporter": [["list"], ["json", {"outputFile": str(OUTPUT / "browser-report.json")}]],
            "outputDir": str(OUTPUT / "browser"),
            "use": {
                "baseURL": "http://127.0.0.1:3000",
                "locale": "en-US",
                "viewport": {"width": 1800, "height": 1200},
                "trace": "off",
                "screenshot": "only-on-failure",
                "launchOptions": {
                    "executablePath": os.getenv("BUSINESS_CHROMIUM_EXECUTABLE")
                    or "/home/huangpan/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
                },
            },
        }
        environment = {
            **os.environ,
            "BUSINESS_SMOKE_USER": "verification-admin",
            "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
            "BUSINESS_TASK_START_REPORT": str(OUTPUT / "acceptance.json"),
        }
        with tempfile.TemporaryDirectory(prefix="business-task-start-") as directory:
            config_path = Path(directory) / "playwright.config.ts"
            config_path.write_text("export default " + json.dumps(browser_config) + ";\n")
            subprocess.run(  # noqa: S603 - local test runner and generated config, no shell.
                [str(ROOT / "src/frontend/node_modules/.bin/playwright"), "test", "--config", str(config_path)],
                cwd=ROOT / "src/frontend",
                env=environment,
                check=True,
            )


if __name__ == "__main__":
    main()
