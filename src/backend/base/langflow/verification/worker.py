"""Single worker submits a durable, release-bound job and reconciles its saved receipt."""

import asyncio
import logging

import httpx
from sqlalchemy import select

from langflow.verification.database import Database, Run
from langflow.verification.settings import VerificationSettings

logger = logging.getLogger(__name__)
TERMINAL_JOBS = {"completed", "failed", "cancelled", "timed_out"}


async def run_once(database: Database, settings: VerificationSettings, http: httpx.AsyncClient) -> bool:
    # Recover tracking after a Worker restart before claiming any new task.
    with database.sessions() as session:
        run_id = session.scalar(select(Run.id).where(Run.status == "running").order_by(Run.created_at).limit(1))
    run_id = run_id or database.claim()
    if run_id is None:
        return False
    headers = {"x-api-key": settings.langflow_api_key.get_secret_value()}
    base = f"{settings.langflow_url}/api/v1/verification/runs/{run_id}"
    try:
        response = await http.get(base + "/job", headers=headers, timeout=settings.request_timeout)
        response.raise_for_status()
        state = response.json()
        if state["status"] == "not_registered":
            # This endpoint uses the job_id assigned at acceptance and a permanent Run start guard.
            response = await http.post(base + "/execute", headers=headers, timeout=settings.request_timeout)
            response.raise_for_status()
            state = response.json()
        if state["status"] in TERMINAL_JOBS:
            database.record_error(
                run_id,
                "needs_confirmation",
                "job_without_receipt",
                "Job ended without 08 committed completion; confirm remote execution",
            )
    except httpx.TransportError:
        # Poll the durable registration next time. Never call the mutable draft-run endpoint.
        logger.warning("Job receipt unavailable; will query the original registration for run %s", run_id)
    except httpx.HTTPStatusError as exc:
        database.record_error(
            run_id,
            "needs_confirmation",
            "job_rejected",
            f"Job endpoint returned {exc.response.status_code}; confirm before rerunning",
        )
    return True


async def serve() -> None:
    settings = VerificationSettings()
    if not settings.langflow_api_key.get_secret_value():
        msg = "VERIFICATION_LANGFLOW_API_KEY is required for the worker"
        raise ValueError(msg)
    database = Database(settings.database_url.get_secret_value(), settings.database_schema)
    async with httpx.AsyncClient(follow_redirects=False) as http:
        while True:
            try:
                from langflow.business.execution import run_once as run_business_once
                if not await run_business_once(database, settings, http):
                    await run_once(database, settings, http)
            except Exception:
                logger.exception("Worker failed; accepted runs remain queryable")
            await asyncio.sleep(settings.poll_interval)


if __name__ == "__main__":
    asyncio.run(serve())
