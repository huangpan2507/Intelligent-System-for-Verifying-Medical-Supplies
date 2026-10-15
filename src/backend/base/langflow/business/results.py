# ruff: noqa: S608 - dataset relations and row identifiers come from DatasetStore.
"""Commit frozen result facts and their provenance before declaring a task completed."""

import json

from sqlalchemy import select

from langflow.business.datasets import ROW_ID, safe_json
from langflow.business.models import BusinessResult, ExternalRequest, ResultEvidence, Task, TaskAssessment
from langflow.business.result_templates import render


def rows(store, dataset_id):
    offset = 0
    while True:
        page = store.page(dataset_id, limit=200, offset=offset)
        yield from page["rows"]
        offset += 200
        if offset >= page["total"]:
            break


def structured(value):
    return json.loads(value) if isinstance(value, str) else value


def persist(runtime):
    """Idempotent per task/output/unit; result and evidence insertions share one transaction."""
    store = runtime.store
    with runtime.database.sessions.begin() as session:
        session.get(Task, runtime.task.id, with_for_update=True)
        assessment = session.get(TaskAssessment, runtime.task.id)
        summary = assessment.summary if assessment else {}
        for node_id, profile in runtime.package.get("result_templates", {}).items():
            unit_ref = runtime.outputs.get(profile["units"]["node"], {}).get(profile["units"]["port"])
            if not unit_ref:
                msg = f"Result units unavailable: {node_id}"
                raise ValueError(msg)
            result_ref = runtime.outputs.get(node_id, {}).get("data")
            answers = {}
            for row in rows(store, result_ref["id"]) if result_ref else []:
                key = row[profile["result_unit_field"]]
                if key in answers:
                    msg = f"Multiple final results for one unit: {node_id}/{key}"
                    raise ValueError(msg)
                answers[key] = row
            audited = {}
            for check in summary.get("checks", []):
                if check.get("dataset_id"):
                    for item in rows(store, check["dataset_id"]):
                        if item["unit_dataset_id"] == unit_ref["id"]:
                            audited.setdefault(item["unit_row_id"], {})[check["name"]] = item
            existing = set(
                session.scalars(
                    select(BusinessResult.unit_row_id).where(
                        BusinessResult.task_id == runtime.task.id,
                        BusinessResult.node_id == node_id,
                        BusinessResult.unit_dataset_id == unit_ref["id"],
                    )
                )
            )
            for unit in rows(store, unit_ref["id"]):
                unit_id = unit[ROW_ID]
                answer = answers.pop(unit_id, None)
                if unit_id in existing:
                    continue
                facts = {k: (answer or unit).get(k) for k in profile["columns"]}
                reasons = {}
                # The coverage audit also represents a unit that never reached Compare.
                for check in profile["checks"]:
                    audit = audited.get(unit_id, {}).get(check["name"], {})
                    if not answer or audit.get("coverage_gap"):
                        facts[check["status"]] = "uncompared"
                    reasons[check["name"]] = audit.get("reason", "missing_result" if not answer else "")
                result = BusinessResult(
                    task_id=runtime.task.id,
                    release_id=runtime.task.release_id,
                    node_id=node_id,
                    template_id=profile["id"],
                    template_version=profile["version"],
                    unit_dataset_id=unit_ref["id"],
                    unit_row_id=unit_id,
                    result_dataset_id=result_ref["id"] if answer else None,
                    result_row_id=answer[ROW_ID] if answer else None,
                    facts=safe_json(facts),
                    **render(profile, facts, reasons=reasons),
                )
                session.add(result)
                session.flush()
                evidence = []
                ref = result_ref if answer else unit_ref
                row_id = answer[ROW_ID] if answer else unit_id
                with store.engine() as db:
                    origins = db.execute(
                        f"SELECT DISTINCT source_dataset_id, source_row_id FROM {store.lineage(ref['id'])} "
                        "WHERE row_id = ?",
                        [row_id],
                    ).fetchall()
                for dataset_id, source_row_id in origins:
                    evidence.append(
                        {
                            "kind": "source",
                            "source_dataset_id": dataset_id,
                            "source_row_id": source_row_id,
                            "context": {},
                        }
                    )
                request_id = facts.get("_request_id")
                if request_id:
                    request = session.get(ExternalRequest, request_id)
                    if request is None or request.task_id != runtime.task.id:
                        msg = "Result recognition request does not belong to this task"
                        raise ValueError(msg)
                    evidence.append(
                        {
                            "kind": "recognition",
                            "request_id": request_id,
                            "context": {"evidence_ref": facts.get("evidence_ref")},
                        }
                    )
                contexts = structured(facts.get("image_manifest_context")) or []
                if not isinstance(contexts, list) or any(not isinstance(c, dict) for c in contexts):
                    msg = "Image evidence must be a list of provenance objects"
                    raise ValueError(msg)
                if answer and (not origins or not request_id or not contexts):
                    msg = "Final result is missing source, recognition or image provenance"
                    raise ValueError(msg)
                evidence.extend(
                    {
                        "kind": "image",
                        "request_id": request_id,
                        "context": {
                            **context,
                            "ORGAN_CODE": facts.get("ORGAN_CODE"),
                            "SYSTEM_ID": facts.get("SYSTEM_ID"),
                            "RPT_NO": context.get("RPT_NO", facts.get("RPT_NO")),
                        },
                    }
                    for context in contexts
                )
                for ordinal, item in enumerate(evidence):
                    session.add(ResultEvidence(result_id=result.id, ordinal=ordinal, **safe_json(item)))
            if answers:
                msg = "Final result references a unit outside the template scope"
                raise ValueError(msg)
