"""Isolated full-stack acceptance using real HTTP, SQLite metadata and synthetic sources.

Does not connect to or migrate the user's existing databases. Does not replace the
separate MySQL/PostgreSQL acceptance check.
"""

import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from langflow.business.templates import consumables

ROOT = Path(__file__).resolve().parents[2]


def request(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    if not response.is_success:
        raise RuntimeError(f"{method} {path}: {response.status_code} {response.text[:1200]}")
    return response.json()


def main():
    directory = Path(tempfile.mkdtemp(prefix="business-smoke-"))
    password, internal, token = (secrets.token_urlsafe(24) for _ in range(3))
    env = {
        **os.environ,
        "LANGFLOW_CONFIG_DIR": str(directory / "platform"),
        "LANGFLOW_DATABASE_URL": f"sqlite:///{directory}/platform.db",
        "LANGFLOW_COMPONENTS_PATH": str(ROOT / "deploy/verification/components"),
        "LANGFLOW_SUPERUSER": "business-test-admin",
        "LANGFLOW_SUPERUSER_PASSWORD": password,
        "LANGFLOW_AUTO_LOGIN": "false",
        "LANGFLOW_CREATE_STARTER_PROJECTS": "false",
        "LANGFLOW_UPDATE_STARTER_PROJECTS": "false",
        "LANGFLOW_LAZY_LOAD_COMPONENTS": "true",
        "LANGFLOW_SKIP_MCP_AUTO_INIT": "true",
        "LANGFLOW_MODELS_DEV_REFRESH": "false",
        "LANGFLOW_DO_NOT_TRACK": "true",
        "VERIFICATION_INTERNAL_TOKEN": internal,
        "VERIFICATION_UPSTREAM_TOKEN": token,
        "VERIFICATION_CLIENTS": json.dumps({"test-system": secrets.token_urlsafe(24)}),
        "VERIFICATION_DEMO_MODE": "true",
        "VERIFICATION_DATABASE_URL": f"sqlite:///{directory}/business.db",
        "VERIFICATION_API_URL": "http://127.0.0.1:18881",
        "VERIFICATION_LANGFLOW_URL": "http://127.0.0.1:17861",
        "BUSINESS_DATA_DIR": str(directory / "datasets"),
        "VITE_PROXY_TARGET": "http://127.0.0.1:17861",
    }
    from langflow.verification.database import Database

    database = Database(env["VERIFICATION_DATABASE_URL"])
    database.initialize()
    database.engine.dispose()
    processes, logs = [], []

    def launch(name, command, cwd=ROOT):
        log = (directory / f"{name}.log").open("w")
        logs.append(log)
        processes.append(
            subprocess.Popen(command, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        )

    def ready(url):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f"Service exited; logs: {directory}")
            try:
                if httpx.get(url, timeout=2).is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise RuntimeError(f"Service timeout: {url}; logs: {directory}")

    try:
        for name, module, port, probe in [
            ("api", "langflow.verification.api:create_app", 18881, "/health"),
            ("demo", "langflow.verification.demo:create_demo_app", 18090, "/openapi.json"),
            ("platform", "langflow.main:create_app", 17861, "/health"),
        ]:
            launch(
                name, [sys.executable, "-m", "uvicorn", module, "--factory", "--host", "127.0.0.1", "--port", str(port)]
            )
            ready(f"http://127.0.0.1:{port}{probe}")
        with httpx.Client(base_url=env["VERIFICATION_LANGFLOW_URL"], timeout=120) as http:
            login = request(
                http, "POST", "/api/v1/login", data={"username": "business-test-admin", "password": password}
            )
            http.headers["Authorization"] = "Bearer " + login["access_token"]
            api_key = request(http, "POST", "/api/v1/api_key/", json={"name": "smoke"})["api_key"]
            connection = request(
                http,
                "POST",
                "/api/v1/business/connections",
                json={
                    "name": "Synthetic",
                    "kind": "api",
                    "config": {"base_url": "http://127.0.0.1:18090"},
                    "secret": token,
                },
            )
            scheme = request(
                http,
                "POST",
                "/api/v1/business/schemes",
                json={
                    "code": "smoke.consumables",
                    "name": "Smoke consumables",
                    "graph": consumables(connection["id"]),
                    "allowed_sources": ["test-system"],
                },
            )
            release = request(
                http,
                "POST",
                "/api/v1/business/schemes/smoke.consumables/releases",
                json={"expected_revision": scheme["revision"]},
            )
            scheme = request(http, "GET", "/api/v1/business/schemes")[0]
            request(
                http,
                "PUT",
                "/api/v1/business/schemes/smoke.consumables/active",
                json={"release_id": release["id"], "expected_revision": scheme["revision"]},
            )
            task = request(
                http,
                "POST",
                "/api/v1/business/tasks",
                headers={"Idempotency-Key": "smoke"},
                json={"scheme": "smoke.consumables", "parameters": {}},
            )
            request(http, "POST", f"/api/v1/business/tasks/{task['id']}/execute", headers={"x-api-key": api_key})
            for _ in range(90):
                task = request(http, "GET", f"/api/v1/business/tasks/{task['id']}")
                if task["status"] not in {"waiting", "running"}:
                    break
                time.sleep(1)
            if task["status"] != "completed":
                raise RuntimeError(f"Task did not complete: {task['status']} {task.get('error')}; logs: {directory}")
            result = next(d for d in task["datasets"] if d["node_id"] == "Results" and d["port"] == "data")
            rows = request(http, "GET", f"/api/v1/business/tasks/{task['id']}/datasets/{result['id']}")["rows"]
            assert {r["_comparison_status"] for r in rows} == {"equal", "different"}
            print("HTTP publication -> durable Job -> generic Graph -> paged results passed", flush=True)
            launch(
                "frontend",
                ["npm", "run", "start", "--", "--host", "127.0.0.1", "--port", "13001", "--strictPort"],
                ROOT / "src/frontend",
            )
            ready("http://127.0.0.1:13001")
            browser_env = {
                **env,
                "BUSINESS_SMOKE_USER": "business-test-admin",
                "BUSINESS_SMOKE_PASSWORD": password,
                "BUSINESS_SMOKE_TASK": task["id"],
                "BUSINESS_SMOKE_FLOW": scheme["flow_id"],
                "BUSINESS_SMOKE_EDGES": str(len(consumables()["edges"])),
                "BUSINESS_SMOKE_RECORDS": str(task["assessment"]["received_records"]),
                "BUSINESS_SMOKE_OUTPUT": str(directory),
            }
            subprocess.run(
                ["node", "scripts/business-smoke.mjs"], cwd=ROOT / "src/frontend", env=browser_env, check=True
            )
            scheme = request(http, "GET", "/api/v1/business/schemes")[0]
            republished = request(
                http,
                "POST",
                "/api/v1/business/schemes/smoke.consumables/releases",
                json={"expected_revision": scheme["revision"]},
            )
            assert len(republished["package"]["graph"]["edges"]) == len(consumables()["edges"])
            print("Saved native canvas republished with all edges intact", flush=True)
        print(f"Acceptance artifacts: {directory}")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
        for log in logs:
            log.close()
        print(f"Logs retained: {directory}")


if __name__ == "__main__":
    main()
