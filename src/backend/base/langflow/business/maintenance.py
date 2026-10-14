"""One intake transaction boundary; accepted work drains on its original running build."""

from sqlalchemy import or_, select, update

from langflow.business.contracts import CONTRACT_VERSION
from langflow.business.models import MigrationState, Release, Scheme, Task
from langflow.verification.database import now


def lock_intake(session):
    # UPDATE obtains a write lock on SQLite too, where SELECT FOR UPDATE is ignored.
    session.execute(update(MigrationState).where(MigrationState.name == "task_intake").values(updated_at=now()))
    return session.get(MigrationState, "task_intake", populate_existing=True)


def pending(session):
    return list(
        session.scalars(
            select(Task.id).where(
                or_(
                    Task.status.in_(["waiting", "running"]),
                    (Task.status == "needs_confirmation") & Task.started.is_(True),
                )
            )
        )
    )


def status(database):
    with database.sessions() as session:
        gate = session.get(MigrationState, "task_intake")
        tasks = pending(session)
        return {"status": gate.status, "pending_tasks": tasks, "safe_to_upgrade": gate.status != "open" and not tasks}


def change(database, action):
    from langflow.business.compiler import runtime_digest

    with database.sessions.begin() as session:
        gate = lock_intake(session)
        if action == "close":
            gate.status = "maintenance"
        elif action == "open":
            if pending(session):
                msg = "Accepted local work has not drained"
                raise ValueError(msg)
            active = session.scalars(select(Release).join(Scheme, Scheme.active_release_id == Release.id))
            if any(
                r.package.get("contract_version", 1) != CONTRACT_VERSION
                or r.package["runtime_digest"] != runtime_digest()
                for r in active
            ):
                msg = "Republish or deactivate incompatible active releases before reopening intake"
                raise ValueError(msg)
            gate.status = "open"
        else:
            msg = "Use close or open"
            raise ValueError(msg)
    return status(database)
