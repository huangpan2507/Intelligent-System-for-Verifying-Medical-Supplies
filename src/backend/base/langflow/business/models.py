"""Additive business tables, independent of historical verification contracts."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from langflow.verification.database import JSON_VALUE, new_id, now


class Base(DeclarativeBase):
    metadata = MetaData(schema="verification")


class Connection(Base):
    __tablename__ = "business_connection"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    config: Mapped[dict] = mapped_column(JSON_VALUE)
    secret: Mapped[str] = mapped_column(String, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Scheme(Base):
    __tablename__ = "business_scheme"
    code: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    flow_id: Mapped[str] = mapped_column(String(36))
    draft: Mapped[dict] = mapped_column(JSON_VALUE)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    active_release_id: Mapped[str | None] = mapped_column(String(36), default=None)
    allowed_sources: Mapped[list] = mapped_column(JSON_VALUE, default=list)


class Release(Base):
    __tablename__ = "business_release"
    __table_args__ = (UniqueConstraint("scheme_code", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scheme_code: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[int] = mapped_column(Integer)
    package: Mapped[dict] = mapped_column(JSON_VALUE)
    content_hash: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Task(Base):
    __tablename__ = "business_task"
    __table_args__ = (UniqueConstraint("source", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(160), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    content_hash: Mapped[str] = mapped_column(String(64))
    scheme_code: Mapped[str] = mapped_column(String(160), index=True)
    release_id: Mapped[str] = mapped_column(String(36))
    parameters: Mapped[dict] = mapped_column(JSON_VALUE)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, default=new_id)
    status: Mapped[str] = mapped_column(String(30), default="waiting", index=True)
    progress: Mapped[dict] = mapped_column(JSON_VALUE, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON_VALUE, default=None)
    results: Mapped[list] = mapped_column(JSON_VALUE, default=list)
    started: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TaskInput(Base):
    """Additive input receipt: historical tasks and tables are left intact."""

    __tablename__ = "business_task_input"
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_task_id: Mapped[str] = mapped_column(String(160), index=True)
    rule_name: Mapped[str] = mapped_column(String(200))


class Dataset(Base):
    __tablename__ = "business_dataset"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    node_id: Mapped[str] = mapped_column(String(160))
    port: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    fields: Mapped[list] = mapped_column(JSON_VALUE)
    row_count: Mapped[int] = mapped_column(Integer)
    raw: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[dict] = mapped_column(JSON_VALUE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MigrationState(Base):
    __tablename__ = "business_migration_state"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExternalRequest(Base):
    __tablename__ = "business_external_request"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    node_id: Mapped[str] = mapped_column(String(160))
    input_dataset_id: Mapped[str] = mapped_column(String(36))
    input_row_id: Mapped[int] = mapped_column(Integer)
    connection_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON_VALUE)
    transport: Mapped[str] = mapped_column(String(30), default="prepared")
    remote: Mapped[str] = mapped_column(String(30), default="unknown")
    validity: Mapped[str] = mapped_column(String(30), default="unassessed")
    response: Mapped[dict] = mapped_column(JSON_VALUE, default=dict)
    error: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TaskAssessment(Base):
    __tablename__ = "business_task_assessment"
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BusinessResult(Base):
    """Frozen business presentation and facts, independent of the source database."""

    __tablename__ = "business_result"
    __table_args__ = (UniqueConstraint("task_id", "node_id", "unit_dataset_id", "unit_row_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("verification.business_task.id"), index=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("verification.business_release.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(160))
    template_id: Mapped[str] = mapped_column(String(100))
    template_version: Mapped[int] = mapped_column(Integer)
    unit_dataset_id: Mapped[str] = mapped_column(ForeignKey("verification.business_dataset.id"))
    unit_row_id: Mapped[int] = mapped_column(BigInteger)
    result_dataset_id: Mapped[str | None] = mapped_column(ForeignKey("verification.business_dataset.id"))
    result_row_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30))
    complete: Mapped[bool] = mapped_column(Boolean)
    narrative: Mapped[str] = mapped_column(String)
    facts: Mapped[dict] = mapped_column(JSON_VALUE)
    checks: Mapped[list] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResultEvidence(Base):
    __tablename__ = "business_result_evidence"
    __table_args__ = (UniqueConstraint("result_id", "ordinal"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    result_id: Mapped[str] = mapped_column(ForeignKey("verification.business_result.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    source_dataset_id: Mapped[str | None] = mapped_column(ForeignKey("verification.business_dataset.id"))
    source_row_id: Mapped[int | None] = mapped_column(BigInteger)
    request_id: Mapped[str | None] = mapped_column(ForeignKey("verification.business_external_request.id"), index=True)
    context: Mapped[dict] = mapped_column(JSON_VALUE)


def initialize(database):
    """Only add new tables. Historical verification tables are never rewritten."""
    Base.metadata.create_all(database.engine)
    from sqlalchemy.exc import IntegrityError

    try:
        with database.sessions.begin() as session:
            for name in ["legacy_intake", "task_intake"]:
                if session.get(MigrationState, name) is None:
                    session.add(MigrationState(name=name))
    except IntegrityError:
        # Another service can initialize the same shared database concurrently.
        pass
