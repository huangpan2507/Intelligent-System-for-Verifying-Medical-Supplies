# ruff: noqa: S101, PLR2004 - actual PostgreSQL acceptance assertions.
"""Check persisted result/evidence joins and repeat saving without invoking any service."""

import json

from langflow.business.models import BusinessResult, Dataset, ExternalRequest, Release, ResultEvidence, Task
from langflow.business.results import persist
from langflow.business.runtime import Runtime
from sqlalchemy import func, inspect, select

from scripts.business.apply_compact_core import local_context
from scripts.business.apply_core_classification import save
from scripts.business.apply_results_configuration import EVIDENCE


def main():
    _, database, settings = local_context()
    try:
        task_id = json.loads((EVIDENCE / "acceptance.json").read_text())["task_id"]
        with database.sessions() as session:
            task = session.get(Task, task_id)
            release = session.get(Release, task.release_id)
            results = list(session.scalars(select(BusinessResult).where(BusinessResult.task_id == task_id)))
            assert len(results) == 2
            evidence = list(
                session.scalars(select(ResultEvidence).where(ResultEvidence.result_id.in_([r.id for r in results])))
            )
            requests_before = session.scalar(
                select(func.count()).select_from(ExternalRequest).where(ExternalRequest.task_id == task_id)
            )
            for item in evidence:
                if item.source_dataset_id:
                    assert session.get(Dataset, item.source_dataset_id).task_id == task_id
                if item.request_id:
                    request = session.get(ExternalRequest, item.request_id)
                    assert request.task_id == task_id
                    assert request.node_id == "Observation"
                    assert request.response
            frozen = {r.id: (r.narrative, r.facts, r.checks) for r in results}
            before_ids = {item.id for item in evidence}
        runtime = Runtime(database, settings, task, release.package)
        runtime.outputs = {node: receipt["outputs"] for node, receipt in task.progress.items() if "outputs" in receipt}
        persist(runtime)
        with database.sessions() as session:
            after = list(session.scalars(select(BusinessResult).where(BusinessResult.task_id == task_id)))
            assert {r.id: (r.narrative, r.facts, r.checks) for r in after} == frozen
            assert (
                set(session.scalars(select(ResultEvidence.id).where(ResultEvidence.result_id.in_(frozen))))
                == before_ids
            )
            assert (
                session.scalar(
                    select(func.count()).select_from(ExternalRequest).where(ExternalRequest.task_id == task_id)
                )
                == requests_before
            )
        metadata = inspect(database.engine)
        tables = ["business_result", "business_result_evidence"]
        report = {
            "task_id": task_id,
            "database": "verification",
            "schema": "verification_scope",
            "result_count": len(results),
            "evidence_count": len(evidence),
            "recognition_requests": 2,
            "idempotent": True,
            "saved_text_unchanged": True,
            "no_external_calls_when_resaving": True,
            "foreign_keys": {name: metadata.get_foreign_keys(name, schema="verification_scope") for name in tables},
            "unique_constraints": {
                name: metadata.get_unique_constraints(name, schema="verification_scope") for name in tables
            },
        }
        save(EVIDENCE / "database-audit.json", report)
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in {"foreign_keys", "unique_constraints"}}, ensure_ascii=False
            )
        )
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
