# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Authenticated business API. Run with uvicorn's --factory option."""

from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID  # noqa: TC003 - FastAPI resolves endpoint annotations at runtime.

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from langflow.verification.database import (
    Artifact,
    Database,
    ExecutionBinding,
    HospitalScope,
    ModelRequest,
    RuleDefinition,
    RuleRelease,
    Run,
    SettlementSnapshot,
    Task,
    fingerprint,
    new_id,
    now,
)
from langflow.verification.schemas import (
    ArtifactWrite,
    ErrorWrite,
    ManualAction,
    RequestResult,
    RequestWrite,
    RerunAction,
    StageUpdate,
    SubmitTask,
    json_value,
)
from langflow.verification.settings import VerificationSettings
from langflow.verification.task_queries import task_evidence, task_results, task_runs

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
        "release_id": run.release_id,
        "binding_id": run.binding_id,
        "job_id": run.job_id,
        "execution_started": run.execution_started,
        "snapshot_id": run.snapshot_id,
        "progress": run.progress,
        "rule_version": run.policy["rule_version"],
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
        "scope": task.payload,
        "current_run_id": task.current_run_id,
        **run_view(run),
    }


def create_app(settings: VerificationSettings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or VerificationSettings()
    database = database or Database(settings.database_url.get_secret_value(), settings.database_schema)
    app = FastAPI(title="Consumable Verification API", version="1.0.0")
    app.state.database = database
    app.state.settings = settings

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

    @app.get("/health")
    def health() -> dict:
        with database.sessions() as session:
            session.execute(select(Task.id).limit(1))
        return {"status": "ok", "contract_version": "range-v1"}

    @app.post(prefix + "/tasks", status_code=202)
    def submit(
        body: SubmitTask,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=160)],
        source: str = source_dep,
    ) -> dict:
        payload = json_value(body)
        digest = fingerprint(payload)

        def existing(session):
            return session.scalar(
                select(Task).where(Task.source_system == source, Task.external_task_id == idempotency_key)
            )

        try:
            with database.sessions.begin() as session:
                task = existing(session)
                if task is not None:
                    if task.content_hash != digest:
                        conflict("Idempotency key already exists with different content")
                    return task_view(session, task)
                hospitals = [
                    h
                    for h in session.scalars(select(HospitalScope))
                    if body.hospital_scope in [h.id, h.name, *h.aliases]
                ]
                if len(hospitals) != 1:
                    raise HTTPException(422, "医院范围未登记或存在歧义")
                hospital = hospitals[0]
                if source not in hospital.allowed_sources:
                    raise HTTPException(403, "来源无权核验该医院范围")
                rules = list(
                    session.scalars(
                        select(RuleDefinition)
                        .where((RuleDefinition.code == body.rule) | (RuleDefinition.name == body.rule))
                        .with_for_update()
                    )
                )
                if len(rules) != 1 or not rules[0].active_binding_id:
                    raise HTTPException(422, "规则未登记、存在歧义或尚未启用")
                rule = rules[0]
                binding = session.get(ExecutionBinding, rule.active_binding_id)
                release = session.get(RuleRelease, binding.release_id)
                if binding.config["simulated"] != settings.demo_mode:
                    conflict("Simulation mode differs from active release")
                task_id, run_id = new_id(), new_id()
                task = Task(
                    id=task_id,
                    source_system=source,
                    external_task_id=idempotency_key,
                    payload={
                        **payload,
                        "hospitals": hospital.members,
                        "hospital_mapping": {"id": hospital.id, "revision": hospital.revision},
                        "rule_code": rule.code,
                    },
                    content_hash=digest,
                    current_run_id=run_id,
                )
                session.add(task)
                session.flush()
                session.add(
                    Run(
                        id=run_id,
                        task_id=task_id,
                        release_id=release.id,
                        binding_id=binding.id,
                        policy={
                            "catalog_mapping": release.package["catalog_mapping"],
                            "rule_version": f"{rule.code}@{release.version}",
                            "currency": release.package["currency"],
                            "money_tolerance": release.package["configurations"]["07"]["money_tolerance"],
                            "simulated": release.package["simulated"],
                        },
                    )
                )
                session.flush()
                return task_view(session, task)
        except IntegrityError:
            with database.sessions() as session:
                task = existing(session)
                if task is None:
                    raise
                if task.content_hash != digest:
                    conflict("Idempotency key already exists with different content")
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
            return task_runs(session, task_for_source(session, str(task_id), source), limit, offset)

    @app.get(prefix + "/tasks/{task_id}/results")
    def results(
        task_id: UUID,
        run_id: UUID | None = None,
        version: Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        source: str = source_dep,
    ) -> dict:
        with database.sessions() as session:
            return task_results(
                session,
                task_for_source(session, str(task_id), source),
                run_id,
                version=version,
                limit=limit,
                offset=offset,
            )

    @app.get(prefix + "/tasks/{task_id}/evidence")
    def evidence(
        task_id: UUID,
        run_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        source: str = source_dep,
    ) -> dict:
        with database.sessions() as session:
            return task_evidence(
                session, task_for_source(session, str(task_id), source), run_id, limit=limit, offset=offset
            )

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
    def rerun(task_id: UUID, body: RerunAction, source: str = source_dep) -> dict:
        with database.sessions.begin() as session:
            task = task_for_source(session, str(task_id), source)
            old = session.get(Run, task.current_run_id)
            if old.status not in {"completed", "partial_failed", "failed"}:
                conflict("Confirm the old execution has ended before requesting a new run")
            snapshot = session.get(SettlementSnapshot, old.snapshot_id) if old.snapshot_id else None
            if not (snapshot and snapshot.sealed) and not body.refetch_unsealed:
                conflict("原结算快照尚未封存，须明确选择重新取数")
            run = Run(
                id=new_id(),
                task_id=task.id,
                release_id=old.release_id,
                binding_id=old.binding_id,
                snapshot_id=snapshot.id if snapshot and snapshot.sealed else None,
                policy=old.policy,
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
            release = session.get(RuleRelease, run.release_id)
            binding = session.get(ExecutionBinding, run.binding_id)
            return {
                **run_view(run),
                "task": task.payload,
                "policy": run.policy,
                "current_run_id": task.current_run_id,
                "configurations": release.package["configurations"],
                "binding": binding.config,
                "content_hash": release.content_hash,
            }

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

    from langflow.verification.release_api import register_release_routes
    from langflow.verification.scope_api import register_scope_routes
    from langflow.verification.task_queries import register_task_query_routes

    register_task_query_routes(app, database, source_dep, internal)
    register_scope_routes(app, database, internal)
    register_release_routes(app, database, settings, internal)
    return app
