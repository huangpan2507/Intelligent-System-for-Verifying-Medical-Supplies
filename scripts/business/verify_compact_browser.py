# ruff: noqa: S603, S607 - local acceptance CLI, no shell or secret output.
"""Inspect the accepted compact canvas in Chromium, without changing local server or database state."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from scripts.business.apply_compact_core import ROOT
from scripts.business.apply_core_classification import save
from scripts.business.apply_study_relevance import EVIDENCE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    evidence = parser.parse_args().evidence_dir.resolve()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    report = {
        **json.loads((evidence / "deployment.json").read_text()),
        **json.loads((evidence / "acceptance.json").read_text()),
    }
    report_path = evidence / "browser-input.json"
    save(report_path, report)
    output = evidence / "browser"
    config = {
        "testDir": str(ROOT / "src/frontend/tests"),
        "testMatch": "core/features/business-compact-core.spec.ts",
        "timeout": 300000,
        "workers": 1,
        "retries": 0,
        "reporter": "list",
        "outputDir": str(output),
        "use": {
            "baseURL": "http://127.0.0.1:3000",
            "locale": "en-US",
            "viewport": {"width": 1600, "height": 1000},
            "actionTimeout": 20000,
            "screenshot": "only-on-failure",
        },
    }
    executable = os.getenv("BUSINESS_CHROMIUM_EXECUTABLE")
    if executable:
        config["use"]["launchOptions"] = {"executablePath": executable}
    env = {
        **os.environ,
        "BUSINESS_SMOKE_USER": "verification-admin",
        "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
        "BUSINESS_COMPACT_REPORT": str(report_path),
    }
    with tempfile.TemporaryDirectory(prefix="compact-browser-") as directory:
        path = Path(directory) / "playwright.config.ts"
        path.write_text("export default " + json.dumps(config) + ";\n")
        subprocess.run(
            ["node_modules/.bin/playwright", "test", "--config", str(path)],
            cwd=ROOT / "src/frontend",
            env=env,
            check=True,
        )
    print(f"Browser acceptance passed; artifacts: {output}")


if __name__ == "__main__":
    main()
