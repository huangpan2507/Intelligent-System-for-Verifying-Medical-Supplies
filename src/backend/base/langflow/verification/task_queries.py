"""Read-only task queries shared by source clients and the rule owner's admin UI."""

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, Query
from sqlalchemy import func, or_, select

from langflow.verification.database import (
    Artifact,
    ModelRequest,
    Result,
    RuleDefinition,
    RuleRelease,
    Run,
    Task,
    VerificationUnit,
)
from langflow.verification.schemas import RunStatus

PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]
Actor = Annotated[str, Header(alias="X-Verification-Actor", min_length=1, max_length=36)]


def visible_tasks(*, source=None, actor=None):
    statement = select(Task, Run).join(Run, Run.id == Task.current_run_id)
    if source is not None:
        return statement.where(Task.source_system == source)
    if actor is None:
        raise HTTPException(403, "Task access requires a source or rule owner")
    return (
        statement.join(RuleRelease, RuleRelease.id == Run.release_id)
        .join(RuleDefinition, RuleDefinition.code == RuleRelease.rule_code)
        .where(RuleDefinition.owner_id == actor)
    )


def owned_task(session, task_id, actor):
    task = session.scalar(visible_tasks(actor=actor).where(Task.id == str(task_id)))
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


def task_list(session, *, source=None, actor=None, status=None, q="", limit=20, offset=0):
    from langflow.verification.api import run_view

    statement = visible_tasks(source=source, actor=actor)
    if status:
        statement = statement.where(Run.status == status)
    if q.strip():
        statement = statement.where(
            or_(
                *(
                    field.icontains(q.strip(), autoescape=True)
                    for field in (
                        Task.id,
                        Task.external_task_id,
                        Task.payload["hospital_scope"].as_string(),
                        Task.payload["rule"].as_string(),
                        Task.payload["rule_code"].as_string(),
                    )
                )
            )
        )
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.execute(statement.order_by(Task.created_at.desc(), Task.id).limit(limit).offset(offset))
    return {
        "items": [
            {
                "source_system": task.source_system,
                "external_task_id": task.external_task_id,
                "scope": task.payload,
                "current_run_id": task.current_run_id,
                **run_view(run),
            }
            for task, run in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def task_runs(session, task, limit, offset):
    from langflow.verification.api import run_view

    return [
        run_view(run)
        for run in session.scalars(
            select(Run)
            .where(Run.task_id == task.id)
            .order_by(Run.created_at.desc(), Run.id)
            .limit(limit)
            .offset(offset)
        )
    ]


def task_results(session, task, run_id=None, *, version=1, limit=50, offset=0):
    from langflow.verification.api import task_view

    view = task_view(session, task, str(run_id) if run_id else None)
    result = session.scalar(select(Result).where(Result.run_id == view["run_id"], Result.version == version))
    return {
        **view,
        "available": result is not None,
        "result_id": result.id if result else None,
        "result_version": result.version if result else None,
        "result": {
            **result.payload,
            "results": list(
                session.scalars(
                    select(VerificationUnit.result)
                    .where(VerificationUnit.run_id == view["run_id"])
                    .order_by(VerificationUnit.id)
                    .limit(limit)
                    .offset(offset)
                )
            ),
            "offset": offset,
            "limit": limit,
        }
        if result
        else None,
    }


def task_evidence(session, task, run_id=None, *, limit=50, offset=0):
    from langflow.verification.api import task_view

    view = task_view(session, task, str(run_id) if run_id else None)
    rid = view["run_id"]
    artifacts = [
        {"artifact_id": a.id, "kind": a.kind, "key": a.key, "payload": a.payload}
        for a in session.scalars(
            select(Artifact).where(Artifact.run_id == rid).order_by(Artifact.id).limit(limit).offset(offset)
        )
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
        for r in session.scalars(
            select(ModelRequest).where(ModelRequest.run_id == rid).order_by(ModelRequest.id).limit(limit).offset(offset)
        )
    ]
    return {
        "task_id": task.id,
        "run_id": rid,
        "artifacts": artifacts,
        "model_requests": requests,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "artifacts_total": session.scalar(select(func.count()).select_from(Artifact).where(Artifact.run_id == rid)),
            "model_requests_total": session.scalar(
                select(func.count()).select_from(ModelRequest).where(ModelRequest.run_id == rid)
            ),
        },
    }


def register_task_query_routes(app, database, source_dep, internal):
    from langflow.verification.api import task_view

    prefix = "/api/v1/verification"

    @app.get(prefix + "/tasks")
    def list_source_tasks(
        status: RunStatus | None = None,
        q: Annotated[str, Query(max_length=200)] = "",
        limit: PageLimit = 20,
        offset: PageOffset = 0,
        source: str = source_dep,
    ):
        with database.sessions() as session:
            return task_list(session, source=source, status=status, q=q, limit=limit, offset=offset)

    @app.get(prefix + "/internal/tasks", dependencies=internal)
    def list_owned_tasks(
        actor: Actor,
        status: RunStatus | None = None,
        q: Annotated[str, Query(max_length=200)] = "",
        limit: PageLimit = 20,
        offset: PageOffset = 0,
    ):
        with database.sessions() as session:
            return task_list(session, actor=actor, status=status, q=q, limit=limit, offset=offset)

    @app.get(prefix + "/internal/tasks/{task_id}", dependencies=internal)
    def get_task(task_id: UUID, actor: Actor, run_id: UUID | None = None):
        with database.sessions() as session:
            return task_view(session, owned_task(session, task_id, actor), str(run_id) if run_id else None)

    @app.get(prefix + "/internal/tasks/{task_id}/runs", dependencies=internal)
    def get_runs(task_id: UUID, actor: Actor, limit: PageLimit = 50, offset: PageOffset = 0):
        with database.sessions() as session:
            return task_runs(session, owned_task(session, task_id, actor), limit, offset)

    @app.get(prefix + "/internal/tasks/{task_id}/results", dependencies=internal)
    def get_results(
        task_id: UUID,
        actor: Actor,
        run_id: UUID | None = None,
        version: Annotated[int, Query(ge=1)] = 1,
        limit: PageLimit = 50,
        offset: PageOffset = 0,
    ):
        with database.sessions() as session:
            return task_results(
                session, owned_task(session, task_id, actor), run_id, version=version, limit=limit, offset=offset
            )

    @app.get(prefix + "/internal/tasks/{task_id}/evidence", dependencies=internal)
    def get_evidence(
        task_id: UUID, actor: Actor, run_id: UUID | None = None, limit: PageLimit = 50, offset: PageOffset = 0
    ):
        with database.sessions() as session:
            return task_evidence(session, owned_task(session, task_id, actor), run_id, limit=limit, offset=offset)
