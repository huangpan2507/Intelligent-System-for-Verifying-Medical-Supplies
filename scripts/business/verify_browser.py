"""Check the running local UI against a synthetic v2 task, without default Playwright server/DB teardown."""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="Reuse an existing demo.consumables.v2 adversarial task")
    args = parser.parse_args()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    token = next(iter(json.loads(private["VERIFICATION_CLIENTS"]).values()))
    port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
    output = ROOT / "deploy/verification/.cache/business-browser-acceptance"
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, timeout=60
    ) as http:
        task_id = args.task
        if not task_id:
            response = http.post(
                "/api/v1/business/tasks",
                headers={"Idempotency-Key": f"browser-acceptance-{uuid4()}"},
                json={"scheme": "demo.consumables.v2", "parameters": {"scenario": "adversarial"}},
            )
            response.raise_for_status()
            task_id = response.json()["id"]
        for _ in range(120):
            response = http.get(f"/api/v1/business/tasks/{task_id}")
            response.raise_for_status()
            task = response.json()
            if task["status"] not in {"waiting", "running"}:
                break
            time.sleep(1)
        assert task["status"] == "completed", task.get("error")
        assert task["scheme_code"] == "demo.consumables.v2"
        assert task["assessment"]["state"] == "accounted"
        assert task["assessment"]["received_records"] == 18

    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=60) as http:
        login = http.post(
            "/api/v1/login",
            data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
        )
        login.raise_for_status()
        http.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        response = http.get("/api/v1/business/schemes")
        response.raise_for_status()
        scheme = next(s for s in response.json() if s["code"] == task["scheme_code"])

    config = {
        "testDir": str(ROOT / "src/frontend/tests"),
        "testMatch": "core/features/business-refactoring.spec.ts",
        "timeout": 300000,
        "workers": 1,
        "retries": 0,
        "reporter": "list",
        "outputDir": str(output),
        "use": {"baseURL": "http://127.0.0.1:3000", "locale": "en-US"},
    }
    executable = os.getenv("BUSINESS_CHROMIUM_EXECUTABLE")
    if executable:
        config["use"]["launchOptions"] = {"executablePath": executable}
    env = {
        **os.environ,
        "BUSINESS_SMOKE_USER": "verification-admin",
        "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
        "BUSINESS_REFACTORING_TASK": task_id,
        "BUSINESS_REFACTORING_FLOW": scheme["flow_id"],
    }
    print(f"Browser acceptance task: {task_id}; artifacts: {output}", flush=True)
    with tempfile.TemporaryDirectory(prefix="business-browser-config-") as directory:
        path = Path(directory) / "playwright.config.ts"
        path.write_text("export default " + json.dumps(config) + ";\n")
        subprocess.run(
            ["node_modules/.bin/playwright", "test", "--config", str(path)],
            cwd=ROOT / "src/frontend",
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
