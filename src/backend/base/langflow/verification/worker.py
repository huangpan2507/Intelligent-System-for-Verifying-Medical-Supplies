"""Single worker: claim once, invoke one fixed flow, check persisted completion."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from langflow.verification.database import Database, Run, Task
from langflow.verification.settings import VerificationSettings

logger = logging.getLogger(__name__)


async def run_once(database: Database, settings: VerificationSettings, http: httpx.AsyncClient) -> bool:
    run_id = database.claim()
    if run_id is None:
        return False
    with database.sessions() as session:
        run = session.get(Run, run_id)
        task = session.get(Task, run.task_id)
        flow_id = run.flow_id
        payload = {"task_id": task.id, "run_id": run.id, "detail_ids": task.payload["detail_ids"]}
    try:
        response = await http.post(
            f"{settings.langflow_url}/api/v1/run/{flow_id}",
            headers={"x-api-key": settings.langflow_api_key.get_secret_value()},
            json={"input_value": json.dumps(payload), "input_type": "any", "output_type": "any", "session_id": run_id},
            timeout=settings.flow_timeout,
        )
        # The platform may have failed after accepting execution. Persistence remains authoritative.
        code = "flow_returned_without_result" if response.is_success else "flow_http_error"
        database.record_error(
            run_id,
            "needs_confirmation",
            code,
            "Flow returned without a committed terminal result; confirm remote execution has ended",
        )
    except httpx.TransportError:
        database.record_error(
            run_id,
            "needs_confirmation",
            "flow_transport_unknown",
            "Flow may have accepted the request; do not automatically resubmit",
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
                worked = await run_once(database, settings, http)
            except Exception:
                # A claimed run is never put back into waiting, even after a DB/process failure.
                logger.exception("Worker failed; verify any last running task manually")
                worked = False
            if not worked:
                await asyncio.sleep(settings.poll_interval)


if __name__ == "__main__":
    asyncio.run(serve())
