"""Run the core-path browser acceptance against the existing local services."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def main():
    private = dotenv_values(ROOT / "deploy/verification/.env")
    output = ROOT / "deploy/business/evidence/core-flow-20261012"
    output.mkdir(parents=True, exist_ok=True)
    config = {
        "testDir": str(ROOT / "src/frontend/tests"),
        "testMatch": "core/features/business-core-flow.spec.ts",
        "timeout": 1800000,
        "workers": 1,
        "retries": 0,
        "reporter": [["list"], ["json", {"outputFile": str(output / "browser-report.json")}]],
        "outputDir": str(output / "browser"),
        "use": {
            "baseURL": "http://127.0.0.1:3000",
            "locale": "en-US",
            "viewport": {"width": 2200, "height": 1400},
            "actionTimeout": 30000,
            "trace": "off",
            "screenshot": "only-on-failure",
            "navigationTimeout": 120000,
            "launchOptions": {
                "executablePath": os.getenv("BUSINESS_CHROMIUM_EXECUTABLE")
                or "/home/huangpan/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
            },
        },
    }
    env = {
        **os.environ,
        "BUSINESS_SMOKE_USER": "verification-admin",
        "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
        "BUSINESS_CORE_EVIDENCE": str(output),
    }
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=60) as http:
        login = http.post(
            "/api/v1/login", data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]}
        )
        login.raise_for_status()
        env["BUSINESS_CORE_TOKEN"] = login.json()["access_token"]
    with tempfile.TemporaryDirectory(prefix="business-core-browser-") as directory:
        path = Path(directory) / "playwright.config.ts"
        path.write_text("export default " + json.dumps(config) + ";\n")
        subprocess.run(  # noqa: S603 - fixed local executable and a configuration created above; no shell.
            [str(ROOT / "src/frontend/node_modules/.bin/playwright"), "test", "--config", str(path)],
            cwd=ROOT / "src/frontend",
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
