"""Authenticated business API. Run with uvicorn's --factory option."""

from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID  # noqa: TC003 - FastAPI resolves endpoint annotations at runtime.

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from langflow.verification.database import Artifact, Database, ModelRequest, Result, Run, Task, fingerprint, new_id, now
from langflow.verification.schemas import (
    ArtifactWrite,
    ErrorWrite,
    FinishRun,
    ManualAction,
    RequestResult,
    RequestWrite,
    StageUpdate,
    SubmitTask,
    json_value,
)
from langflow.verification.settings import VerificationSettings

AUTH = HTTPBearer()
Credentials = Annotated[HTTPAuthorizationCredentials, Depends(AUTH)]


def conflict(message: str) -> None:
    raise HTTPException(409, message)


def task_for_source(session, task_id: str, source: str) -> Task:
    task = session.scalar(select(Task).where(Task.id == task_id, Task.source_system == source).with_for_update())
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


def active_run(session, run_id: str) -> Run:
    task = session.scalar(select(Task).join(Run, Run.task_id == Task.id).where(Run.id == run_id).with_for_update())
    if task is None:
        raise HTTPException(404, "Run not found")
    run = session.get(Run, run_id)
    if task.current_run_id != run_id or run.status != "running":
        conflict("Run is no longer active; a manual rerun never accepts late writes")
    return run


def run_view(run: Run) -> dict:
    return {
        "run_id": run.id,
        "task_id": run.task_id,
        "status": run.status,
        "stage": run.stage,
        "stage_event": run.stage_event,
        "flow_id": run.flow_id,
        "error": run.error,
        "manual_action": run.manual_action,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def task_view(session, task: Task, run_id: str | None = None) -> dict:
    run = session.get(Run, run_id or task.current_run_id)
    if run is None or run.task_id != task.id:
        raise HTTPException(404, "Run not found")
    return {
        "source_system": task.source_system,
        "external_task_id": task.external_task_id,
        "detail_ids": task.payload["detail_ids"],
        "current_run_id": task.current_run_id,
        **run_view(run),
    }


def create_app(settings: VerificationSettings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or VerificationSettings()
    database = database or Database(settings.database_url.get_secret_value(), settings.database_schema)
    app = FastAPI(title="Consumable Verification API", version="1.0.0")
    app.state.database = database

    def source_auth(credentials: Credentials) -> str:
        for source, token in settings.clients.items():
            if secrets.compare_digest(credentials.credentials, token.get_secret_value()):
                return source
        raise HTTPException(401, "Invalid client credential")

    def internal_auth(credentials: Credentials) -> None:
        if not secrets.compare_digest(credentials.credentials, settings.internal_token.get_secret_value()):
            raise HTTPException(401, "Invalid service credential")

    source_dep = Depends(source_auth)
    internal = [Depends(internal_auth)]
    prefix = "/api/v1/verification"

    def policy() -> dict:
        return {
            "catalog_mapping": settings.catalog_mapping,
            "rule_version": settings.rule_version,
            "currency": settings.currency,
            "money_tolerance": str(settings.money_tolerance),
            "simulated": settings.demo_mode,
        }

    @app.get("/health")
    def health() -> dict:
        with database.sessions() as session:
            session.execute(select(Task.id).limit(1))
        return {"status": "ok", "contract_version": "1"}

    @app.post(prefix + "/tasks", status_code=202)
    def submit(body: SubmitTask, source: str = source_dep) -> dict:
        if body.source_system != source:
            raise HTTPException(403, "Source does not match credential")
        payload = json_value(body)
        digest = fingerprint(payload)

        def existing(session) -> Task | None:
            return session.scalar(
                select(Task).where(Task.source_system == source, Task.external_task_id == body.external_task_id)
            )

        try:
            with database.sessions.begin() as session:
                task = existing(session)
                if task is None:
                    task_id, run_id = new_id(), new_id()
                    task = Task(
                        id=task_id,
                        source_system=source,
                        external_task_id=body.external_task_id,
                        payload=payload,
                        content_hash=digest,
                        current_run_id=run_id,
                    )
                    session.add(task)
                    session.flush()
                    session.add(Run(id=run_id, task_id=task_id, flow_id=settings.flow_id, policy=policy()))
                    session.flush()
                elif task.content_hash != digest:
                    conflict("External task ID already exists with different content")
                return task_view(session, task)
        except IntegrityError:
            # Concurrent inserts are serialized by the database's source/reference constraint.
            with database.sessions() as session:
                task = existing(session)
                if task is None:
                    raise
                if task.content_hash != digest:
                    conflict("External task ID already exists with different content")
                return task_view(session, task)

    @app.get(prefix + "/tasks/by-reference/{external_task_id}")
    def by_reference(external_task_id: str, source: str = source_dep) -> dict:
        with database.sessions() as session:
            task = session.scalar(
                select(Task).where(Task.source_system == source, Task.external_task_id == external_task_id)
            )
            if task is None:
                raise HTTPException(404, "Task not found")
            return task_view(session, task)

    @app.get(prefix + "/tasks/{task_id}")
    def get_task(task_id: UUID, run_id: UUID | None = None, source: str = source_dep) -> dict:
        with database.sessions() as session:
            task = task_for_source(session, str(task_id), source)
            return task_view(session, task, str(run_id) if run_id else None)

    @app.get(prefix + "/tasks/{task_id}/runs")
    def get_runs(
        task_id: UUID,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        source: str = source_dep,
    ) -> list[dict]:
        with database.sessions() as session:
            task_for_source(session, str(task_id), source)
            return [
                run_view(run)
                for run in session.scalars(
                    select(Run)
                    .where(Run.task_id == str(task_id))
                    .order_by(Run.created_at.desc(), Run.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get(prefix + "/tasks/{task_id}/results")
    def results(
        task_id: UUID,
        run_id: UUID | None = None,
        version: Annotated[int, Query(ge=1)] = 1,
        source: str = source_dep,
    ) -> dict:
        with database.sessions() as session:
            task = task_for_source(session, str(task_id), source)
            view = task_view(session, task, str(run_id) if run_id else None)
            result = session.scalar(select(Result).where(Result.run_id == view["run_id"], Result.version == version))
            return {
                **view,
                "available": result is not None,
                "result_id": result.id if result else None,
                "result_version": result.version if result else None,
                "result": result.payload if result else None,
            }

    @app.get(prefix + "/tasks/{task_id}/evidence")
    def evidence(task_id: UUID, run_id: UUID | None = None, source: str = source_dep) -> dict:
        with database.sessions() as session:
            task = task_for_source(session, str(task_id), source)
            view = task_view(session, task, str(run_id) if run_id else None)
            rid = view["run_id"]
            artifacts = [
                {"artifact_id": a.id, "kind": a.kind, "key": a.key, "payload": a.payload}
                for a in session.scalars(select(Artifact).where(Artifact.run_id == rid))
            ]
            requests = [
                {
                    "request_id": r.id,
                    "scope_id": r.scope_id,
                    "input": r.payload,
                    "status": r.status,
                    "model_job_id": r.model_job_id,
                    "raw_response": r.raw_response,
                    "error": r.error,
                }
                for r in session.scalars(select(ModelRequest).where(ModelRequest.run_id == rid))
            ]
            return {"task_id": str(task_id), "run_id": rid, "artifacts": artifacts, "model_requests": requests}

    @app.post(prefix + "/tasks/{task_id}/runs/{run_id}/confirmation")
    def confirm(task_id: UUID, run_id: UUID, body: ManualAction, source: str = source_dep) -> dict:
        with database.sessions.begin() as session:
            task = task_for_source(session, str(task_id), source)
            run = session.get(Run, str(run_id))
            if run is None or run.task_id != task.id:
                raise HTTPException(404, "Run not found")
            if run.id != task.current_run_id or run.status not in {"running", "needs_confirmation", "failed"}:
                conflict("Only the current interrupted or failed execution can be confirmed")
            run.status = "failed"
            run.manual_action = {**json_value(body), "source_system": source, "confirmed_at": now().isoformat()}
            run.finished_at = now()
            return run_view(run)

    @app.post(prefix + "/tasks/{task_id}/runs", status_code=202)
    def rerun(task_id: UUID, body: ManualAction, source: str = source_dep) -> dict:
        with database.sessions.begin() as session:
            task = task_for_source(session, str(task_id), source)
            old = session.get(Run, task.current_run_id)
            if old.status not in {"completed", "partial_failed", "failed"}:
                conflict("Confirm the old execution has ended before requesting a new run")
            run = Run(
                id=new_id(),
                task_id=task.id,
                flow_id=settings.flow_id,
                policy=policy(),
                manual_action={**json_value(body), "previous_run_id": old.id, "source_system": source},
            )
            session.add(run)
            task.current_run_id = run.id
            session.flush()
            return task_view(session, task)

    @app.get(prefix + "/internal/runs/{run_id}", dependencies=internal)
    def context(run_id: UUID) -> dict:
        with database.sessions() as session:
            run = session.get(Run, str(run_id))
            if run is None:
                raise HTTPException(404, "Run not found")
            task = session.get(Task, run.task_id)
            return {**run_view(run), "task": task.payload, "policy": run.policy, "current_run_id": task.current_run_id}

    @app.post(prefix + "/internal/runs/{run_id}/stages", dependencies=internal)
    def stage(run_id: UUID, body: StageUpdate) -> dict:
        with database.sessions.begin() as session:
            run = active_run(session, str(run_id))
            if body.event == "started":
                expected = 1 if run.stage is None else int(run.stage) + 1
                if int(body.stage) != expected or (run.stage is not None and run.stage_event != "finished"):
                    conflict("Stage cannot be restarted, skipped, or run concurrently")
            elif run.stage != body.stage or run.stage_event != "started" or body.stage == "08":
                conflict("Stage completion does not match the active stage; 08 requires a result receipt")
            run.stage, run.stage_event = body.stage, body.event
            return {"saved": True, "run_id": run.id, "stage": run.stage, "event": run.stage_event}

    @app.post(prefix + "/internal/runs/{run_id}/artifacts", dependencies=internal)
    def artifact(run_id: UUID, body: ArtifactWrite) -> dict:
        with database.sessions.begin() as session:
            active_run(session, str(run_id))
            record = session.scalar(
                select(Artifact).where(
                    Artifact.run_id == str(run_id), Artifact.kind == body.kind, Artifact.key == body.key
                )
            )
            if record:
                if record.payload != body.payload:
                    conflict("Saved evidence is immutable")
            else:
                record = Artifact(run_id=str(run_id), **json_value(body))
                session.add(record)
                session.flush()
            return {"saved": True, "artifact_id": record.id}

    @app.post(prefix + "/internal/runs/{run_id}/requests", dependencies=internal, status_code=201)
    def register_request(run_id: UUID, body: RequestWrite) -> dict:
        with database.sessions.begin() as session:
            run = active_run(session, str(run_id))
            if run.stage != "06" or run.stage_event != "started":
                conflict("Recognition requests may only be registered during stage 06")
            exists = session.scalar(
                select(ModelRequest).where(
                    (ModelRequest.id == str(body.request_id))
                    | ((ModelRequest.run_id == str(run_id)) & (ModelRequest.scope_id == body.scope_id))
                )
            )
            if exists:
                conflict("Recognition already registered; never automatically resubmit")
            session.add(
                ModelRequest(id=str(body.request_id), run_id=str(run_id), scope_id=body.scope_id, payload=body.payload)
            )
            return {"saved": True, "request_id": str(body.request_id)}

    @app.put(prefix + "/internal/runs/{run_id}/requests/{request_id}", dependencies=internal)
    def request_result(run_id: UUID, request_id: UUID, body: RequestResult) -> dict:
        with database.sessions.begin() as session:
            active_run(session, str(run_id))
            record = session.get(ModelRequest, str(request_id))
            if record is None or record.run_id != str(run_id):
                raise HTTPException(404, "Recognition request not found")
            values = json_value(body)
            if record.status != "registered" and any(getattr(record, k) != v for k, v in values.items()):
                conflict("Recognition response already saved")
            for key, value in values.items():
                setattr(record, key, value)
            return {"saved": True, "request_id": record.id}

    @app.post(prefix + "/internal/runs/{run_id}/errors", dependencies=internal)
    def error(run_id: UUID, body: ErrorWrite) -> dict:
        with database.sessions.begin() as session:
            run = active_run(session, str(run_id))
            run.status = body.status
            run.error = {"code": body.code, "message": body.message}
            run.finished_at = now()
        return {"saved": True}

    @app.post(prefix + "/internal/runs/{run_id}/results", dependencies=internal)
    def finish(run_id: UUID, body: FinishRun) -> dict:
        payload = json_value(body)
        with database.sessions.begin() as session:
            # Lock the task before checking for an idempotent result receipt.
            task = session.scalar(
                select(Task).join(Run, Run.task_id == Task.id).where(Run.id == str(run_id)).with_for_update()
            )
            if task is None:
                raise HTTPException(404, "Run not found")
            result = session.scalar(select(Result).where(Result.run_id == str(run_id), Result.version == 1))
            if result:
                if result.payload != payload:
                    conflict("Result version is immutable")
                return {"saved": True, "result_id": result.id, "result_version": 1, "run_id": str(run_id)}
            run = active_run(session, str(run_id))
            if run.stage != "08" or run.stage_event != "started":
                conflict("Results require stage 08")
            details = [detail for item in body.results for detail in item.get("detail_ids", [])]
            if sorted(details) != sorted(task.payload["detail_ids"]):
                conflict("Results must cover each accepted settlement detail exactly once")
            saved = {a.kind: a.payload for a in session.scalars(select(Artifact).where(Artifact.run_id == run.id))}
            if not {"settlement_snapshot", "manifest", "comparison"}.issubset(saved):
                conflict("Required snapshots, manifests and comparison evidence must be saved first")
            if saved["comparison"] != payload or body.rule_version != run.policy["rule_version"]:
                conflict("Result does not match the saved comparison or pinned rules")
            if body.simulated != run.policy["simulated"]:
                conflict("Simulation marker must match the accepted run")
            unresolved = session.scalar(
                select(ModelRequest.id).where(
                    ModelRequest.run_id == run.id, ModelRequest.status.in_(["registered", "needs_confirmation"])
                )
            )
            if unresolved:
                conflict("A recognition request still needs confirmation")
            states = [item.get("execution_status") for item in body.results]
            if any(state not in {"completed", "failed", "partial_failed"} for state in states):
                conflict("Invalid per-scope execution status")
            run.status = (
                "failed"
                if all(s == "failed" for s in states)
                else "partial_failed"
                if any(s != "completed" for s in states)
                else "completed"
            )
            run.stage_event, run.finished_at = "finished", now()
            result = Result(run_id=run.id, version=1, payload=payload)
            session.add(result)
            session.flush()
            return {"saved": True, "result_id": result.id, "result_version": 1, "run_id": run.id}

    return app
