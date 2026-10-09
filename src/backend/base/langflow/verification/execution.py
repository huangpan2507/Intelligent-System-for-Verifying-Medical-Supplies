# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Execute an accepted immutable graph using Langflow's durable background job runner."""

import asyncio
import contextlib
import copy
import json
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from langflow.verification.database import fingerprint
from langflow.verification.releases import require_runtime


async def submit_execution(execution, user):
    from langflow.services.database.models.jobs.model import JobStatus
    from langflow.services.deps import get_background_execution_service, get_job_service

    jobs = get_job_service()
    job_id = UUID(execution["job_id"])
    existing = await jobs.get_job_by_job_id(job_id)
    if existing:
        return {"job_id": str(job_id), "status": existing.status}
    if (
        execution["execution_started"]
        or execution["status"] != "running"
        or execution["current_run_id"] != execution["run_id"]
    ):
        raise HTTPException(409, "运行已执行或不再处于领取状态，不能重新启动")
    package = execution["package"]
    if fingerprint(package) != execution["content_hash"]:
        raise HTTPException(409, "发布包内容摘要不匹配")
    try:
        require_runtime(package)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    request = {
        "verification_run_id": execution["run_id"],
        "session_id": execution["run_id"],
        "stream_protocol": "langflow",
        "content_hash": execution["content_hash"],
    }
    try:
        await jobs.create_job(job_id=job_id, flow_id=UUID(package["flow_id"]), user_id=user.id, request=request)
    except IntegrityError:
        existing = await jobs.get_job_by_job_id(job_id)
        if existing is None:
            raise
        return {"job_id": str(job_id), "status": existing.status}
    service = get_background_execution_service()
    await service.start()
    # The original immutable request is persisted atomically with the job row. A crash before
    # enqueue leaves QUEUED work for the existing startup reconciliation, never a new job id.
    await service._enqueue(  # noqa: SLF001 - Reuse the durable runner for the pre-registered job.
        job_id=job_id, flow_id=UUID(package["flow_id"]), request=request, user=user
    )
    return {"job_id": str(job_id), "status": JobStatus.QUEUED}


def frame_source(*, request, user):
    async def source(*, job_id=None, **_kwargs):
        from lfx.graph import Graph

        from langflow.api.v1.verification import business
        from langflow.verification.pipeline import Pipeline
        from langflow.verification.settings import FlowSettings

        run_id = request["verification_run_id"]
        execution = await business("GET", f"/runs/{run_id}/execution")
        package = execution["package"]
        if (
            execution["job_id"] != str(job_id)
            or package["owner_id"] != str(user.id)
            or execution["content_hash"] != request["content_hash"]
            or fingerprint(package) != request["content_hash"]
        ):
            msg = "Job does not match immutable release binding"
            raise ValueError(msg)
        require_runtime(package)
        settings = FlowSettings()
        if settings.demo_mode != package["simulated"]:
            msg = "Runtime and release simulation modes differ"
            raise ValueError(msg)
        await business("POST", f"/runs/{run_id}/execution/start")
        try:
            graph = Graph.from_payload(
                copy.deepcopy(package["graph"]),
                flow_id=UUID(str(job_id)),
                user_id=str(user.id),
                flow_name=f"verification:{run_id}",
            )
            entry = {key: execution[key] for key in ["task_id", "run_id", "release_id", "job_id"]}
            # Fresh Graph, unique cache/session namespace and no tweaks/global defaults.
            await graph.arun(inputs=[{"input_value": json.dumps(entry)}], types=["any"], session_id=run_id)
            async with httpx.AsyncClient(follow_redirects=False) as http:
                saved = await Pipeline(settings, http).internal("GET", run_id)
            if saved["stage"] != "08" or saved["stage_event"] != "finished":
                msg = "Graph ended without the 08 business receipt"
                raise ValueError(msg)
            yield (
                (
                    "data: "
                    + json.dumps(
                        {
                            "event": "output",
                            "data": {
                                "run_id": run_id,
                                "job_id": str(job_id),
                                "release_id": execution["release_id"],
                                "business_status": saved["status"],
                            },
                        }
                    )
                    + "\n\n"
                ).encode(),
                "output",
            )
        except BaseException:
            # Cancellation/worker loss must never imply that the remote model has stopped.
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    business(
                        "POST",
                        f"/runs/{run_id}/errors",
                        payload={
                            "status": "needs_confirmation",
                            "code": "job_interrupted",
                            "message": "Execution interrupted; confirm remote processing before rerunning",
                        },
                    )
                )
            raise

    return source
