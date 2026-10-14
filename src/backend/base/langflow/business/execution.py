"""Use the platform's durable background Job instead of request-local background tasks."""

import json
from uuid import UUID

import httpx
from sqlalchemy import select

from langflow.business.models import Task
from langflow.verification.database import Database, now
from langflow.verification.settings import VerificationSettings


def database_and_settings():
    settings = VerificationSettings()
    return Database(settings.database_url.get_secret_value(), settings.database_schema), settings


async def submit_execution(task_id, user):
    from fastapi import HTTPException

    from langflow.services.deps import get_background_execution_service, get_job_service

    database, _settings = database_and_settings()
    try:
        with database.sessions() as session:
            task = session.get(Task, task_id)
            if not task or task.owner_id != str(user.id):
                raise HTTPException(404, "Task not found")
            from langflow.business.models import Release

            release = session.get(Release, task.release_id)
        jobs = get_job_service()
        existing = await jobs.get_job_by_job_id(UUID(task.job_id))
        if existing:
            return {"job_id": task.job_id, "status": existing.status}
        if task.started or task.status not in {"waiting", "running"}:
            raise HTTPException(409, "Task cannot be started again")
        request = {"business_task_id": task.id, "session_id": task.id, "stream_protocol": "langflow"}
        await jobs.create_job(
            job_id=UUID(task.job_id), flow_id=UUID(release.package["flow_id"]), user_id=user.id, request=request
        )
        service = get_background_execution_service()
        await service.start()
        await service._enqueue(  # noqa: SLF001 - Same durable-job enqueue contract as verification jobs.
            job_id=UUID(task.job_id), flow_id=UUID(release.package["flow_id"]), request=request, user=user
        )
        return {"job_id": task.job_id, "status": "queued"}
    finally:
        database.engine.dispose()


def frame_source(*, request, user):
    async def source(*, job_id=None, **_kwargs):
        from langflow.business.runtime import run_task

        database, settings = database_and_settings()
        try:
            with database.sessions() as session:
                task = session.get(Task, request["business_task_id"])
                if not task or task.owner_id != str(user.id) or task.job_id != str(job_id):
                    msg = "Job does not own this business task"
                    raise ValueError(msg)
            await run_task(database, settings, task.id)
            yield (
                ("data: " + json.dumps({"event": "output", "data": {"task_id": task.id}}) + "\n\n").encode(),
                "output",
            )
        finally:
            database.engine.dispose()

    return source


async def run_once(database, settings, http):
    from langflow.business.models import initialize

    initialize(database)
    with database.sessions.begin() as session:
        task = session.scalar(
            select(Task).where(Task.status.in_(["waiting", "running"])).order_by(Task.created_at).limit(1)
        )
        if task is None:
            return False
        if task.status == "waiting":
            task.status = "running"
        task_id = task.id
    headers = {"x-api-key": settings.langflow_api_key.get_secret_value()}
    try:
        response = await http.post(
            f"{settings.langflow_url}/api/v1/business/tasks/{task_id}/execute", headers=headers, timeout=60
        )
        response.raise_for_status()
        if response.json()["status"] in {"failed", "cancelled", "timed_out", "completed"}:
            with database.sessions.begin() as session:
                task = session.get(Task, task_id)
                if task.status == "running":
                    task.status = "needs_confirmation"
                    task.error = {"type": "missing_receipt", "message": "Job ended without a complete dataset receipt"}
                    task.finished_at = now()
    except httpx.HTTPStatusError as exc:
        with database.sessions.begin() as session:
            task = session.get(Task, task_id)
            task.status = "needs_confirmation"
            task.error = {"type": "job_rejected", "message": f"HTTP {exc.response.status_code}"}
    except httpx.TransportError:
        pass
    return True
