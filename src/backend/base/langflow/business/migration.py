"""Drain legacy acceptance without rewriting releases, tasks, snapshots or evidence."""

from fastapi import HTTPException
from sqlalchemy import select

from langflow.business.models import MigrationState
from langflow.verification.database import Run, now


def require_legacy_intake(session):
    state = session.get(MigrationState, "legacy_intake", with_for_update=True)
    if state and state.status != "open":
        raise HTTPException(410, "Legacy workflows are read-only; submit to /api/v1/business/tasks with a scheme code")


def require_legacy_confirmation(session):
    state = session.get(MigrationState, "legacy_intake", with_for_update=True)
    if state and state.status == "complete":
        raise HTTPException(410, "Legacy migration is complete; historical executions are read-only")


def stop_legacy_intake(database):
    # Acceptance takes the same row lock, so no new task can cross this boundary.
    with database.sessions.begin() as session:
        state = session.get(MigrationState, "legacy_intake", with_for_update=True)
        if state.status != "complete":
            state.status = "draining"
            state.updated_at = now()
    with database.sessions.begin() as session:
        pending = list(
            session.scalars(
                select(Run.id).where(
                    Run.status.in_(["waiting", "running"])
                    | ((Run.status == "needs_confirmation") & Run.execution_started.is_(True))
                )
            )
        )
        if pending:
            return {"status": "draining", "pending_runs": pending}
        state = session.get(MigrationState, "legacy_intake", with_for_update=True)
        state.status = "complete"
        state.updated_at = now()
        # A rejected, never-started run cannot acquire the legacy start guard:
        # active_run requires status="running". Preserve its historical status.
        unstarted = list(
            session.scalars(select(Run.id).where(Run.status == "needs_confirmation", Run.execution_started.is_(False)))
        )
        return {"status": "complete", "pending_runs": [], "unstarted_historical_runs": unstarted}
