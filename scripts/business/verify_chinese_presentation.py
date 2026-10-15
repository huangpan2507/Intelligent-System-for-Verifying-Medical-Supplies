"""Read-only browser acceptance for Business Chinese presentation."""

import json
import os
import subprocess
from pathlib import Path

import httpx
from langflow.business.components import from_langflow

from scripts.business.apply_compact_core import local_context, login
from scripts.business.apply_core_classification import call
from scripts.business.verify_result_evidence import snapshot

ROOT = Path(__file__).resolve().parents[2]
FLOW = "ce588a72-0614-4d84-badd-0e4355c427e6"
TASK = "7a36ff98-fdc5-4475-ab01-13a5bc59f406"


def main():
    output = ROOT / "deploy/business/evidence/chinese-presentation-20261015"
    output.mkdir(parents=True, exist_ok=True)
    private, database, _settings = local_context()
    try:
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=60) as http:
            login(http, private)
            before = from_langflow(call(http, "GET", f"/api/v1/flows/{FLOW}")["data"])
            before_counts = snapshot(database, TASK)
            configuration = {
                "testDir": str(ROOT / "src/frontend/tests"),
                "testMatch": "core/features/business-chinese-presentation.spec.ts",
                "timeout": 240000,
                "workers": 1,
                "retries": 0,
                "reporter": "list",
                "outputDir": str(output / "browser"),
                "use": {
                    "baseURL": "http://127.0.0.1:3000",
                    "viewport": {"width": 1700, "height": 1100},
                    "actionTimeout": 20000,
                    "screenshot": "only-on-failure",
                },
            }
            config_path = output / "playwright.config.ts"
            config_path.write_text("export default " + json.dumps(configuration) + ";\n")
            env = {
                **os.environ,
                "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "deploy/verification/.cache/playwright"),
                "BUSINESS_SMOKE_USER": "verification-admin",
                "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
                "BUSINESS_FLOW_ID": FLOW,
            }
            result = subprocess.run(  # noqa: S603 - fixed local acceptance test; credentials stay in the environment.
                [str(ROOT / "src/frontend/node_modules/.bin/playwright"), "test", "--config", str(config_path)],
                cwd=ROOT / "src/frontend",
                env=env,
                check=False,
            )
            after = from_langflow(call(http, "GET", f"/api/v1/flows/{FLOW}")["data"])
            report = {
                "flow_id": FLOW,
                "ui_exit_code": result.returncode,
                "graph_unchanged": before == after,
                "tasks_results_requests_unchanged": before_counts == snapshot(database, TASK),
            }
            (output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            if not report["graph_unchanged"] or not report["tasks_results_requests_unchanged"]:
                raise RuntimeError("Read-only presentation acceptance changed saved business state")
            raise SystemExit(result.returncode)
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
