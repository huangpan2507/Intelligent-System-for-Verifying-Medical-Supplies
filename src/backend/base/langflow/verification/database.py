"""Business database. Transactions never span HTTP or model execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    create_engine,
    event,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.schema import CreateSchema


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def fingerprint(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Base(DeclarativeBase):
    metadata = MetaData(schema="verification")


JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (UniqueConstraint("source_system", "external_task_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_system: Mapped[str] = mapped_column(String(160))
    external_task_id: Mapped[str] = mapped_column(String(160))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON_VALUE)
    current_run_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("verification.task.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="waiting", index=True)
    stage: Mapped[str | None] = mapped_column(String(2), default=None)
    stage_event: Mapped[str | None] = mapped_column(String(10), default=None)
    flow_id: Mapped[str] = mapped_column(String(160))
    policy: Mapped[dict] = mapped_column(JSON_VALUE)
    error: Mapped[dict | None] = mapped_column(JSON_VALUE, default=None)
    manual_action: Mapped[dict | None] = mapped_column(JSON_VALUE, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Artifact(Base):
    __tablename__ = "artifact"
    __table_args__ = (UniqueConstraint("run_id", "kind", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("verification.run.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelRequest(Base):
    __tablename__ = "model_request"
    __table_args__ = (UniqueConstraint("run_id", "scope_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("verification.run.id"), index=True)
    scope_id: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON_VALUE)
    status: Mapped[str] = mapped_column(String(30), default="registered")
    model_job_id: Mapped[str | None] = mapped_column(String(160), default=None)
    raw_response: Mapped[dict | None] = mapped_column(JSON_VALUE, default=None)
    error: Mapped[str | None] = mapped_column(String(2000), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Result(Base):
    __tablename__ = "result"
    __table_args__ = (UniqueConstraint("run_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("verification.run.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Database:
    def __init__(self, url: str, schema: str = "verification"):
        self.schema = None if url.startswith("sqlite") else schema
        options = {"connect_args": {"check_same_thread": False}} if self.schema is None else {}
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            execution_options={"schema_translate_map": {"verification": self.schema}},
            **options,
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        if self.schema is None:
            event.listen(self.engine, "connect", self._sqlite_foreign_keys)

    @staticmethod
    def _sqlite_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    def initialize(self) -> None:
        """Bootstrap only an empty, separately owned business schema (version 1)."""
        if self.schema:
            with self.engine.begin() as connection:
                connection.execute(CreateSchema(self.schema, if_not_exists=True))
        Base.metadata.create_all(self.engine)

    def claim(self) -> str | None:
        with self.sessions.begin() as session:
            candidate = session.scalar(
                select(Run.id).where(Run.status == "waiting").order_by(Run.created_at, Run.id).limit(1)
            )
            if candidate is None:
                return None
            claimed = session.execute(
                update(Run)
                .where(Run.id == candidate, Run.status == "waiting")
                .values(status="running", started_at=now())
            )
            return candidate if claimed.rowcount == 1 else None

    def record_error(self, run_id: str, status: str, code: str, message: str) -> None:
        with self.sessions.begin() as session:
            session.execute(
                update(Run)
                .where(Run.id == run_id, Run.status == "running")
                .values(status=status, error={"code": code, "message": message}, finished_at=now())
            )


if __name__ == "__main__":
    from langflow.verification.settings import VerificationSettings

    settings = VerificationSettings()
    Database(settings.database_url.get_secret_value(), settings.database_schema).initialize()
