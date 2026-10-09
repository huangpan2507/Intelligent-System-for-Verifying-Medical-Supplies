# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Persist bounded settlement pages and verification units, with complete coverage checks."""

from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Query
from sqlalchemy import select

from langflow.verification.database import (
    Artifact,
    ModelRequest,
    Result,
    ReviewDetail,
    ReviewRecord,
    Run,
    SettlementSnapshot,
    SnapshotDetail,
    Task,
    VerificationUnit,
    fingerprint,
    now,
)
from langflow.verification.schemas import Settlement, SettlementTimeRange, SnapshotPageWrite, UnitWrite

MAX_UNIT_DETAILS = 100


def register_scope_routes(app, database, dependencies):
    from langflow.verification.api import active_run, conflict

    prefix = "/api/v1/verification/internal/runs/{run_id}"

    def stage_run(session, run_id, expected):
        run = active_run(session, str(run_id))
        if run.stage != expected or run.stage_event != "started":
            conflict(f"Operation requires stage {expected}")
        return run

    def get_snapshot(session, run):
        snapshot = session.get(SettlementSnapshot, run.snapshot_id) if run.snapshot_id else None
        if snapshot is None or not snapshot.sealed:
            conflict("Settlement discovery has not been sealed")
        return snapshot

    @app.post(prefix + "/snapshot/pages", dependencies=dependencies)
    def snapshot_page(run_id: UUID, body: SnapshotPageWrite):
        with database.sessions.begin() as session:
            run = stage_run(session, run_id, "01")
            task = session.get(Task, run.task_id)
            bounds = SettlementTimeRange.model_validate(task.payload["settlement_time_range"])
            hospitals = {h["settlement_id"] for h in task.payload["hospitals"]}
            snapshot = session.get(SettlementSnapshot, run.snapshot_id) if run.snapshot_id else None
            if snapshot is None:
                if body.cursor is not None:
                    conflict("First page cannot have a cursor")
                snapshot = SettlementSnapshot(
                    run_id=run.id, snapshot_token=body.snapshot_token, consistency=body.consistency, cursor=None
                )
                session.add(snapshot)
                session.flush()
                run.snapshot_id = snapshot.id
            if (
                snapshot.sealed
                or snapshot.exhausted
                or snapshot.cursor != body.cursor
                or snapshot.snapshot_token != body.snapshot_token
                or snapshot.consistency != body.consistency
                or body.simulated != run.policy["simulated"]
            ):
                conflict("Snapshot page changed source, cursor, consistency or mode")
            if body.next_cursor is not None and (not body.items or body.next_cursor == body.cursor):
                conflict("Source pagination did not advance")
            for item in body.items:
                row = Settlement.model_validate(item)
                if (
                    row.hospital_id not in hospitals
                    or row.settlement_time is None
                    or not (bounds.start_inclusive <= row.settlement_time < bounds.end_exclusive)
                ):
                    conflict("Source returned a settlement outside the accepted hospital/time range")
                data = row.model_dump(mode="json")
                existing = session.scalar(
                    select(SnapshotDetail).where(
                        SnapshotDetail.snapshot_id == snapshot.id, SnapshotDetail.detail_id == row.detail_id
                    )
                )
                if existing:
                    if existing.payload != data:
                        conflict("Source returned conflicting values for the same detail")
                    continue
                mapping = session.get(ReviewDetail, row.detail_id)
                record = session.get(ReviewRecord, mapping.review_id) if mapping else None
                review = record.payload if record and record.simulated == run.policy["simulated"] else None
                # No review means no validated counting scope. Keep facts separate from rule configuration.
                key = (
                    "review-" + fingerprint({"id": mapping.review_id})
                    if review
                    else "group-"
                    + fingerprint(
                        {
                            "patient": row.patient_id,
                            "hospital": row.hospital_id,
                            "encounter": row.encounter_id,
                            "encounter_type": row.encounter_type,
                            "category": run.policy["catalog_mapping"].get(row.catalog_code),
                            "unit": row.unit,
                            "side": row.raw.get("side"),
                            "unidentified": row.detail_id
                            if not all([row.patient_id, row.encounter_id, row.hospital_id])
                            else None,
                        }
                    )
                )
                session.add(
                    SnapshotDetail(
                        snapshot_id=snapshot.id, detail_id=row.detail_id, payload=data, review=review, unit_key=key
                    )
                )
                snapshot.count += 1
            snapshot.cursor = body.next_cursor
            snapshot.exhausted = body.next_cursor is None
            run.progress = {**run.progress, "discovered": snapshot.count, "discovery_complete": False}
            return {"saved": True, "snapshot_id": snapshot.id, "count": snapshot.count}

    @app.post(prefix + "/snapshot/seal", dependencies=dependencies)
    def seal(run_id: UUID):
        with database.sessions.begin() as session:
            run = stage_run(session, run_id, "01")
            snapshot = session.get(SettlementSnapshot, run.snapshot_id) if run.snapshot_id else None
            if snapshot is None or not snapshot.exhausted:
                conflict("All settlement pages must succeed before sealing")
            snapshot.sealed = True
            run.progress = {**run.progress, "discovered": snapshot.count, "discovery_complete": True}
            session.add(
                Artifact(
                    run_id=run.id,
                    kind="settlement_snapshot",
                    key="main",
                    payload={
                        "snapshot_id": snapshot.id,
                        "count": snapshot.count,
                        "consistency": snapshot.consistency,
                        "snapshot_token": snapshot.snapshot_token,
                        "simulated": run.policy["simulated"],
                    },
                )
            )
            return {"saved": True, "snapshot_id": snapshot.id, "count": snapshot.count}

    @app.get(prefix + "/snapshot", dependencies=dependencies)
    def snapshot_info(run_id: UUID):
        with database.sessions() as session:
            run = active_run(session, str(run_id))
            snapshot = session.get(SettlementSnapshot, run.snapshot_id) if run.snapshot_id else None
            return {
                "snapshot_id": snapshot.id if snapshot else None,
                "sealed": bool(snapshot and snapshot.sealed),
                "count": snapshot.count if snapshot else 0,
            }

    @app.post(prefix + "/snapshot/reuse", dependencies=dependencies)
    def reuse(run_id: UUID):
        with database.sessions.begin() as session:
            run = stage_run(session, run_id, "01")
            snapshot = get_snapshot(session, run)
            run.progress = {**run.progress, "discovered": snapshot.count, "discovery_complete": True}
            session.add(
                Artifact(
                    run_id=run.id,
                    kind="settlement_snapshot",
                    key="main",
                    payload={"snapshot_id": snapshot.id, "reused": True, "count": snapshot.count},
                )
            )
            return {"saved": True, "snapshot_id": snapshot.id}

    @app.get(prefix + "/unit-source", dependencies=dependencies)
    def unit_source(run_id: UUID, after: str = ""):
        with database.sessions() as session:
            run = stage_run(session, run_id, "02")
            snapshot = get_snapshot(session, run)
            key = session.scalar(
                select(SnapshotDetail.unit_key)
                .where(SnapshotDetail.snapshot_id == snapshot.id, SnapshotDetail.unit_key > after)
                .order_by(SnapshotDetail.unit_key)
                .limit(1)
            )
            if key is None:
                return {"unit": None}
            rows = list(
                session.scalars(
                    select(SnapshotDetail)
                    .where(SnapshotDetail.snapshot_id == snapshot.id, SnapshotDetail.unit_key == key)
                    .order_by(SnapshotDetail.detail_id)
                    .limit(MAX_UNIT_DETAILS + 1)
                )
            )
            if len(rows) > MAX_UNIT_DETAILS:
                conflict("业务核验单元超过首期100条上限，不能按技术分页拆开计数范围")
            review = rows[0].review
            # A review covering out-of-range records is not valid for a truncated in-range group.
            if review and sorted(review["detail_ids"]) != sorted(r.detail_id for r in rows):
                review = None
            return {"unit": {"key": key, "settlements": [r.payload for r in rows], "review": review}}

    @app.post(prefix + "/units", dependencies=dependencies)
    def create_unit(run_id: UUID, body: UnitWrite):
        with database.sessions.begin() as session:
            run = stage_run(session, run_id, "02")
            snapshot = get_snapshot(session, run)
            ids = list(
                session.scalars(
                    select(SnapshotDetail.detail_id).where(
                        SnapshotDetail.snapshot_id == snapshot.id, SnapshotDetail.unit_key == body.key
                    )
                )
            )
            groups = body.payload.get("groups", [])
            if len(groups) != 1 or sorted(groups[0]["detail_ids"]) != sorted(ids) or not ids:
                conflict("Unit must contain its entire sealed business group exactly once")
            if session.scalar(
                select(VerificationUnit.id).where(VerificationUnit.run_id == run.id, VerificationUnit.key == body.key)
            ):
                conflict("Unit already saved")
            unit = VerificationUnit(run_id=run.id, key=body.key, payload=body.payload)
            session.add(unit)
            session.flush()
            run.progress = {**run.progress, "units": run.progress.get("units", 0) + 1}
            return {"saved": True, "unit_id": unit.id}

    @app.get(prefix + "/units", dependencies=dependencies)
    def units(run_id: UUID, after: Annotated[int, Query(ge=0)] = 0):
        with database.sessions() as session:
            run = active_run(session, str(run_id))
            unit = session.scalar(
                select(VerificationUnit)
                .where(VerificationUnit.run_id == run.id, VerificationUnit.id > after)
                .order_by(VerificationUnit.id)
                .limit(1)
            )
            return {
                "unit": {"id": unit.id, "key": unit.key, "payload": unit.payload, "stage": unit.stage} if unit else None
            }

    @app.put(prefix + "/units/{unit_id}", dependencies=dependencies)
    def save_unit(run_id: UUID, unit_id: int, body: UnitWrite):
        with database.sessions.begin() as session:
            run = active_run(session, str(run_id))
            unit = session.get(VerificationUnit, unit_id)
            if unit is None or unit.run_id != run.id:
                raise HTTPException(404, "Unit not found")
            if (
                run.stage not in {"03", "04", "05", "06", "07"}
                or run.stage_event != "started"
                or int(unit.stage) + 1 != int(run.stage)
            ):
                conflict("Unit stage skipped or repeated")
            if body.key != unit.key or body.payload["settlements"] != unit.payload["settlements"]:
                conflict("Unit settlement snapshot is immutable")
            if len(body.payload.get("groups", [])) != 1:
                conflict("Each persisted unit must contain exactly one business group")
            if sorted(body.payload["groups"][0]["detail_ids"]) != sorted(unit.payload["groups"][0]["detail_ids"]):
                conflict("Unit membership is immutable")
            if run.stage == "07":
                comparison = session.scalar(
                    select(Artifact).where(
                        Artifact.run_id == run.id, Artifact.kind == "comparison", Artifact.key == unit.key
                    )
                )
                if (
                    comparison is None
                    or comparison.payload != body.payload["result"]
                    or body.payload["result"]["rule_version"] != run.policy["rule_version"]
                    or body.payload["result"]["simulated"] != run.policy["simulated"]
                ):
                    conflict("Unit result must match saved evidence and its pinned release")
                result = body.payload["result"]["results"]
                if len(result) != 1 or sorted(result[0]["detail_ids"]) != sorted(
                    unit.payload["groups"][0]["detail_ids"]
                ):
                    conflict("Unit result must cover exactly its sealed details")
                if result[0].get("execution_status") not in {"completed", "partial_failed", "failed"}:
                    conflict("Invalid unit result state")
                unit.result = result[0]
            unit.payload, unit.stage = body.payload, run.stage
            field = f"stage_{run.stage}_processed"
            run.progress = {**run.progress, field: run.progress.get(field, 0) + 1}
            return {"saved": True, "unit_id": unit.id}

    @app.post(prefix + "/results", dependencies=dependencies)
    def finish(run_id: UUID):
        with database.sessions.begin() as session:
            task = session.scalar(
                select(Task).join(Run, Run.task_id == Task.id).where(Run.id == str(run_id)).with_for_update()
            )
            if task is None:
                raise HTTPException(404, "Run not found")
            existing = session.scalar(select(Result).where(Result.run_id == str(run_id)))
            if existing:
                return {"saved": True, "result_id": existing.id, "result_version": 1, "run_id": str(run_id)}
            run = stage_run(session, run_id, "08")
            snapshot = get_snapshot(session, run)
            missing = session.scalar(
                select(SnapshotDetail.id)
                .outerjoin(
                    VerificationUnit,
                    (VerificationUnit.run_id == run.id) & (VerificationUnit.key == SnapshotDetail.unit_key),
                )
                .where(
                    SnapshotDetail.snapshot_id == snapshot.id,
                    (VerificationUnit.id.is_(None))
                    | (VerificationUnit.stage != "07")
                    | VerificationUnit.result.is_(None),
                )
                .limit(1)
            )
            if missing:
                conflict("08 cannot finish until every sealed detail has a terminal unit result")
            if session.scalar(
                select(ModelRequest.id)
                .where(ModelRequest.run_id == run.id, ModelRequest.status.in_(["registered", "needs_confirmation"]))
                .limit(1)
            ):
                conflict("Recognition acceptance remains unknown")
            summary = {
                "details": snapshot.count,
                "units": 0,
                "difference": 0,
                "consistent": 0,
                "not_compared": 0,
                "failed": 0,
                "partial_failed": 0,
                "empty": snapshot.count == 0,
            }
            results = session.scalars(
                select(VerificationUnit.result)
                .where(VerificationUnit.run_id == run.id)
                .execution_options(yield_per=100)
            )
            for result in results:
                if not result:
                    conflict("Unit comparison is missing")
                summary["units"] += 1
                conclusion = result["conclusion"]
                if conclusion in summary:
                    summary[conclusion] += 1
                state = result["execution_status"]
                if state in {"failed", "partial_failed"}:
                    summary[state] += 1
            run.status = (
                "failed"
                if summary["units"] and summary["failed"] == summary["units"]
                else "partial_failed"
                if summary["failed"] or summary["partial_failed"]
                else "completed"
            )
            run.stage_event, run.finished_at = "finished", now()
            result = Result(
                run_id=run.id,
                payload={
                    "summary": summary,
                    "snapshot_id": snapshot.id,
                    "rule_version": run.policy["rule_version"],
                    "release_id": run.release_id,
                    "binding_id": run.binding_id,
                    "job_id": run.job_id,
                    "simulated": run.policy["simulated"],
                },
            )
            session.add(result)
            session.flush()
            return {"saved": True, "result_id": result.id, "result_version": 1, "run_id": run.id}
