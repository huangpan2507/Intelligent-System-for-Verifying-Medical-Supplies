# ruff: noqa: S101, PLR2004 - read-only acceptance assertions against the local core task.
"""Verify saved source relationships and the live evidence UI without executing a task."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
from langflow.business.models import BusinessResult, ExternalRequest, ResultEvidence, Task
from sqlalchemy import func, select

from scripts.business.apply_compact_core import local_context, login
from scripts.business.apply_core_classification import call

ROOT = Path(__file__).resolve().parents[2]


def snapshot(database, task_id):
    with database.sessions() as session:
        rows = list(session.scalars(select(BusinessResult).where(BusinessResult.task_id == task_id)))
        evidence = list(
            session.scalars(select(ResultEvidence).where(ResultEvidence.result_id.in_([r.id for r in rows])))
        )
        records = [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in [*rows, *evidence]]
        payload = json.dumps(sorted(records, key=lambda r: r["id"]), default=str, sort_keys=True)
        return {
            "results": len(rows),
            "evidence": len(evidence),
            "hash": hashlib.sha256(payload.encode()).hexdigest(),
            "all_requests": session.scalar(select(func.count()).select_from(ExternalRequest)),
            "all_tasks": session.scalar(select(func.count()).select_from(Task)),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--flow-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    private, database, _ = local_context()
    before = snapshot(database, args.task_id)
    report = {"task_id": args.task_id, "flow_id": args.flow_id, "before": before, "results": []}
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=90) as http:
        login(http, private)

        def get(path):
            return call(http, "GET", "/api/v1/business/" + path)

        flow = call(http, "GET", f"/api/v1/flows/{args.flow_id}")
        assert len(flow["data"]["nodes"]) == 11
        results = get(f"tasks/{args.task_id}/results")["items"]
        for result in results:
            base = f"tasks/{args.task_id}/results/{result['id']}"
            view = get(base + "/evidence-view")
            assert view["counts"]["unlinked"] == 0
            assert view["counts"]["settlement"] == 1
            source = get(base + f"/evidence/{view['items'][0]['id']}/detail")
            assert source["record"]["RPT_NO"] == result["facts"]["RPT_NO"]
            studies = get(base + "/evidence-view?group=study")["items"]
            image_count = 0
            for study in studies:
                series = get(base + f"/evidence-view?group=series&parent={study['id']}")["items"]
                assert len(series) == study["children"]
                for sequence in series:
                    images = get(base + f"/evidence-view?group=image&parent={sequence['id']}")["items"]
                    image_count += len(images)
                    for image in images:
                        assert image["sources"]
                        for ref in image["sources"]:
                            raw = get(base + f"/evidence/{ref}/detail")
                            assert raw["original_record"]["file_path"] in image["details"]["address"]
            assert image_count == view["counts"]["image"]
            recognition = get(base + "/evidence-view?group=recognition")["items"]
            request = get(base + f"/evidence/{recognition[0]['id']}/detail")["request"]
            assert request["response"]["recognized_category"] == result["facts"]["recognized_category"]
            assert len(result["facts"]) == 44
            report["results"].append({"category": result["facts"]["target_category"], "counts": view["counts"]})
        report["storage"] = get(f"tasks/{args.task_id}/result-storage?node_id=Results")
        assert report["storage"]["saved"] == 2
        report_path = args.output.resolve() / "acceptance.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        if args.browser:
            environment = {
                **os.environ,
                "BUSINESS_EVIDENCE_REPORT": str(report_path),
                "BUSINESS_SMOKE_USER": "verification-admin",
                "BUSINESS_SMOKE_PASSWORD": private["LANGFLOW_SUPERUSER_PASSWORD"],
            }
            subprocess.run(  # noqa: S603 - fixed local Playwright command, no shell.
                [
                    shutil.which("npx"),
                    "playwright",
                    "test",
                    "tests/core/features/business-result-evidence.spec.ts",
                    "--workers=1",
                    "--retries=0",
                    "--reporter=list",
                    f"--output={args.output.resolve() / 'browser'}",
                ],
                cwd=ROOT / "src/frontend",
                env=environment,
                check=True,
            )
        report["after"] = snapshot(database, args.task_id)
        assert before == report["after"], "Read-only evidence viewing changed saved results or triggered execution"
        report["read_only_verified"] = True
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"results": report["results"], "read_only_verified": True}, ensure_ascii=False))
    database.engine.dispose()


if __name__ == "__main__":
    main()
