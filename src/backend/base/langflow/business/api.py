# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Owner management facade and source-isolated public business task queries."""

from typing import Annotated, Literal

import duckdb
import jsonschema
from fastapi import Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from langflow.business.catalog import CATALOG
from langflow.business.compiler import inspect_graph
from langflow.business.connections import encrypt, metadata
from langflow.business.contracts import (
    CONTRACT_VERSION,
    Activate,
    ConnectionWrite,
    DraftWrite,
    Publish,
    SchemeWrite,
    SubmitTask,
)
from langflow.business.datasets import DatasetStore, safe_json
from langflow.business.models import (
    BusinessResult,
    Connection,
    Dataset,
    ExternalRequest,
    Release,
    ResultEvidence,
    Scheme,
    Task,
    TaskAssessment,
    TaskInput,
    initialize,
)
from langflow.business.task_input import CONTEXT, CONTRACT, PARAMETERS, accepted_input, validate_request
from langflow.verification.database import fingerprint, new_id


def view(row):
    value = {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != "secret"}
    return safe_json(value)


def owned(session, cls, key, actor):
    row = session.get(cls, key)
    if row is None or row.owner_id != actor:
        raise HTTPException(404, "Resource not found")
    return row


def task_view(session, task):
    scheme = session.get(Scheme, task.scheme_code)
    return {
        **view(task),
        "flow_id": scheme.flow_id if scheme else None,
        "task_input": accepted_input(session, task),
    }


def register(app, database, settings, internal_auth, source_auth):
    initialize(database)
    internal = "/api/v1/business/internal"
    public = "/api/v1/business"
    dependencies = [Depends(internal_auth)]
    actor_type = Annotated[str, Header(alias="X-Business-Actor", min_length=1, max_length=36)]
    source_dep = Depends(source_auth)

    @app.get(internal + "/maintenance", dependencies=dependencies)
    def maintenance_status(_actor: actor_type):
        from langflow.business.maintenance import status

        return status(database)

    @app.post(internal + "/maintenance", dependencies=dependencies)
    def maintenance_change(body: dict, _actor: actor_type):
        from langflow.business.maintenance import change

        try:
            return change(database, body.get("action"))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post(internal + "/migration", dependencies=dependencies)
    def migrate(_actor: actor_type):
        from langflow.business.migration import stop_legacy_intake

        return stop_legacy_intake(database)

    @app.get(internal + "/catalog", dependencies=dependencies)
    def catalog(_actor: actor_type):
        return {
            "nodes": CATALOG,
            "sources": list(settings.clients),
            "task_input": {"contract": CONTRACT, "parameters": PARAMETERS, "context": CONTEXT},
        }

    @app.get(internal + "/connections", dependencies=dependencies)
    def connections(actor: actor_type):
        with database.sessions() as session:
            return [
                view(row)
                for row in session.scalars(
                    select(Connection).where(Connection.owner_id == actor).order_by(Connection.name)
                )
            ]

    @app.post(internal + "/connections", dependencies=dependencies, status_code=201)
    def create_connection(body: ConnectionWrite, actor: actor_type):
        if any(key in body.config for key in ["password", "secret", "token", "api_key"]):
            raise HTTPException(422, "Credentials must use the separate secret field")
        if body.kind in {"mysql", "postgresql"} and not all(
            body.config.get(k) for k in ["host", "database", "username"]
        ):
            raise HTTPException(422, "Database host, database and username are required")
        if body.kind in {"api", "model"}:
            from urllib.parse import urlparse

            url = urlparse(body.config.get("base_url", ""))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise HTTPException(422, "Use an HTTP(S) base URL without embedded credentials")
        with database.sessions.begin() as session:
            row = Connection(
                owner_id=actor,
                name=body.name,
                kind=body.kind,
                config=body.config,
                secret=encrypt(body.secret, settings),
            )
            session.add(row)
            session.flush()
            return view(row)

    @app.get(internal + "/connections/{connection_id}/schema", dependencies=dependencies)
    def connection_schema(connection_id: str, actor: actor_type, table: str | None = None, schema: str | None = None):
        with database.sessions() as session:
            connection = owned(session, Connection, connection_id, actor)
        try:
            return metadata(connection, settings, table, schema or None)
        except Exception as exc:
            raise HTTPException(
                422, f"Cannot inspect connection ({type(exc).__name__}); check connection configuration"
            ) from exc

    @app.post(internal + "/inspect", dependencies=dependencies)
    def inspect(body: dict, actor: actor_type):
        try:
            return inspect_graph(body["graph"], database, settings, actor, strict=False)
        except Exception as exc:
            raise HTTPException(422, str(exc)[:1000]) from exc

    @app.post(internal + "/connections/{connection_id}/preview", dependencies=dependencies)
    def connection_preview(connection_id: str, body: dict, actor: actor_type):
        from langflow.business.connections import preview
        from langflow.business.field_schema import api_preview, sample_evidence

        with database.sessions() as session:
            connection = owned(session, Connection, connection_id, actor)
        try:
            config = {**body["config"], "connection": connection_id}
            if connection.kind == "api":
                return api_preview(
                    connection, settings, config, body.get("parameters", {}), body.get("record", {}), actor
                )
            result = preview(connection, settings, config, body.get("parameters", {}))
            if config.get("sql"):
                result["field_evidence"] = sample_evidence(config, result["fields"], connection, settings, actor)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, str(exc)[:500]) from exc
        except Exception as exc:
            raise HTTPException(
                422, f"Preview failed ({type(exc).__name__}); check query, bindings and connection"
            ) from exc
        else:
            return result

    @app.post(internal + "/connections/{connection_id}/contract", dependencies=dependencies)
    def connection_contract(connection_id: str, body: dict, actor: actor_type):
        from langflow.business.field_schema import document_evidence, fields_from_schema

        with database.sessions() as session:
            connection = owned(session, Connection, connection_id, actor)
        if connection.kind != "api":
            raise HTTPException(422, "Choose an API connection")
        try:
            config = {**body["config"], "connection": connection_id}
            fields = fields_from_schema(body["document"], config) if "document" in body else body["fields"]
            evidence = document_evidence(config, fields, body.get("reference"))
        except (ValueError, KeyError, TypeError, jsonschema.ValidationError) as exc:
            raise HTTPException(422, str(exc).split("\n")[0][:500]) from exc
        else:
            return {"fields": fields, "field_evidence": evidence}

    @app.post(internal + "/files", dependencies=dependencies)
    async def upload(actor: actor_type, file: UploadFile = File(...)):
        from langflow.business.sources import file_path, file_relation

        suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
        if suffix not in {"csv", "json", "parquet"}:
            raise HTTPException(422, "Use CSV, JSON or Parquet")
        file_id = new_id()
        path = file_path(actor, file_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with path.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    path.unlink(missing_ok=True)
                    raise HTTPException(413, "Upload exceeds 100 MB; use a database source for larger datasets")
                stream.write(chunk)
        with duckdb.connect() as db:
            fields = [
                {"name": r[0], "type": r[1], "nullable": r[2] != "NO"}
                for r in db.execute(f"DESCRIBE SELECT * FROM {file_relation(path, suffix)}").fetchall()
            ]
        from langflow.business.compiler import sql_type

        type_names = {
            "BIGINT": "integer",
            "DECIMAL(38,6)": "number",
            "DOUBLE": "number",
            "BOOLEAN": "boolean",
            "DATE": "date",
            "TIMESTAMP": "datetime",
            "TIMESTAMPTZ": "datetime",
        }
        for field in fields:
            field["type"] = type_names.get(sql_type(field["type"]), "text")
        return {"file_id": file_id, "format": suffix, "name": file.filename, "fields": fields}

    @app.get(internal + "/schemes", dependencies=dependencies)
    def schemes(actor: actor_type):
        with database.sessions() as session:
            return [
                view(s) for s in session.scalars(select(Scheme).where(Scheme.owner_id == actor).order_by(Scheme.name))
            ]

    @app.post(internal + "/schemes", dependencies=dependencies, status_code=201)
    def create_scheme(body: SchemeWrite, actor: actor_type):
        if set(body.allowed_sources) - set(settings.clients):
            raise HTTPException(422, "Unknown source")
        try:
            with database.sessions.begin() as session:
                row = Scheme(
                    code=body.code,
                    name=body.name,
                    owner_id=actor,
                    flow_id=body.flow_id,
                    draft=body.graph.model_dump(),
                    allowed_sources=body.allowed_sources,
                )
                session.add(row)
                session.flush()
                return view(row)
        except IntegrityError as exc:
            raise HTTPException(409, "Scheme code already exists") from exc

    @app.put(internal + "/schemes/{code}/draft", dependencies=dependencies)
    def draft(code: str, body: DraftWrite, actor: actor_type):
        with database.sessions.begin() as session:
            row = owned(session, Scheme, code, actor)
            if row.revision != body.expected_revision:
                raise HTTPException(409, "Draft changed; reload before saving")
            changed = session.execute(
                update(Scheme)
                .where(Scheme.code == code, Scheme.revision == body.expected_revision)
                .values(draft=body.graph.model_dump(), revision=Scheme.revision + 1)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Draft changed; reload before saving")
            session.refresh(row)
            return view(row)

    @app.post(internal + "/schemes/{code}/releases", dependencies=dependencies, status_code=201)
    def publish(code: str, body: Publish, actor: actor_type):
        with database.sessions() as session:
            scheme = owned(session, Scheme, code, actor)
        if scheme.revision != body.expected_revision:
            raise HTTPException(409, "Draft changed")
        try:
            package = inspect_graph(scheme.draft, database, settings, actor)
        except Exception as exc:
            raise HTTPException(422, str(exc)[:2000]) from exc
        package["flow_id"] = scheme.flow_id
        with database.sessions.begin() as session:
            scheme = session.scalar(select(Scheme).where(Scheme.code == code).with_for_update())
            if scheme.revision != body.expected_revision:
                raise HTTPException(409, "Draft changed during validation")
            version = (session.scalar(select(func.max(Release.version)).where(Release.scheme_code == code)) or 0) + 1
            row = Release(
                scheme_code=code, version=version, package=package, content_hash=fingerprint(package), note=body.note
            )
            session.add(row)
            session.flush()
            return view(row)

    @app.get(internal + "/schemes/{code}/releases", dependencies=dependencies)
    def releases(code: str, actor: actor_type):
        with database.sessions() as session:
            owned(session, Scheme, code, actor)
            return [
                view(r)
                for r in session.scalars(
                    select(Release).where(Release.scheme_code == code).order_by(Release.version.desc())
                )
            ]

    @app.post(internal + "/schemes/{code}/releases/from/{release_id}", dependencies=dependencies, status_code=201)
    def republish(code: str, release_id: str, body: Publish, actor: actor_type):
        # Upgrade from an explicitly selected immutable release; never substitute a newer draft.
        with database.sessions() as session:
            scheme = owned(session, Scheme, code, actor)
            previous = session.get(Release, release_id)
            if previous is None or previous.scheme_code != code:
                raise HTTPException(404, "Release not found")
        try:
            from langflow.business.validate_migration import ISSUES_VERSION, migrate_graph

            graph = previous.package["graph"]
            if previous.package.get("validate_issues_version", 1) < ISSUES_VERSION:
                graph = migrate_graph(graph)
            package = inspect_graph(graph, database, settings, actor)
        except Exception as exc:
            raise HTTPException(422, str(exc)[:2000]) from exc
        package["flow_id"] = previous.package.get("flow_id", scheme.flow_id)
        with database.sessions.begin() as session:
            scheme = session.scalar(select(Scheme).where(Scheme.code == code).with_for_update())
            if scheme.revision != body.expected_revision:
                raise HTTPException(409, "Scheme changed")
            version = (session.scalar(select(func.max(Release.version)).where(Release.scheme_code == code)) or 0) + 1
            release = Release(
                scheme_code=code,
                version=version,
                package=package,
                content_hash=fingerprint(package),
                note=body.note or f"Validated from release {release_id}",
            )
            session.add(release)
            session.flush()
            return view(release)

    @app.put(internal + "/schemes/{code}/active", dependencies=dependencies)
    def activate(code: str, body: Activate, actor: actor_type):
        with database.sessions.begin() as session:
            row = owned(session, Scheme, code, actor)
            if row.revision != body.expected_revision:
                raise HTTPException(409, "Scheme changed")
            if body.release_id:
                release = session.get(Release, body.release_id)
                if release is None or release.scheme_code != code:
                    raise HTTPException(404, "Release not found")
            changed = session.execute(
                update(Scheme)
                .where(Scheme.code == code, Scheme.revision == body.expected_revision)
                .values(active_release_id=body.release_id, revision=Scheme.revision + 1)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Scheme changed; reload before activating")
            session.refresh(row)
            return view(row)

    def submit_task(body, source, key, actor=None):
        # Preserve the fingerprint of pre-existing generic requests.
        content_hash = fingerprint(body.model_dump(exclude_none=True))
        try:
            with database.sessions.begin() as session:
                existing = session.scalar(select(Task).where(Task.source == source, Task.idempotency_key == key))
                if existing:
                    if existing.content_hash != content_hash:
                        raise HTTPException(409, "Idempotency key has different content")
                    return task_view(session, existing)
                from langflow.business.maintenance import lock_intake

                if lock_intake(session).status != "open":
                    raise HTTPException(503, "Maintenance: new tasks are paused; accepted tasks continue")
                scheme = session.get(Scheme, body.scheme)
                if (
                    not scheme
                    or (actor and scheme.owner_id != actor)
                    or (not actor and source not in scheme.allowed_sources)
                ):
                    raise HTTPException(404, "Scheme not found")
                if not scheme.active_release_id:
                    raise HTTPException(422, "Scheme has no active release")
                release = session.get(Release, scheme.active_release_id)
                from langflow.business.compiler import runtime_digest

                if (
                    release.package.get("contract_version", 1) != CONTRACT_VERSION
                    or release.package["runtime_digest"] != runtime_digest()
                ):
                    raise HTTPException(409, "Runtime changed; publish a new release")
                from langflow.business.contracts import normalize_parameters

                try:
                    if release.package.get("task_input") == CONTRACT:
                        parameters = validate_request(body.parameters, body.external_task_id)
                    else:
                        if body.external_task_id is not None:
                            msg = "external_task_id requires a regulatory Task Start workflow"
                            raise ValueError(msg)
                        parameters = normalize_parameters(release.package["parameters"], body.parameters)
                except (jsonschema.ValidationError, ValueError) as exc:
                    detail = exc.message if isinstance(exc, jsonschema.ValidationError) else str(exc)
                    raise HTTPException(422, detail) from exc
                row = Task(
                    owner_id=scheme.owner_id,
                    source=source,
                    idempotency_key=key,
                    content_hash=content_hash,
                    scheme_code=scheme.code,
                    release_id=release.id,
                    parameters=parameters,
                )
                session.add(row)
                session.flush()
                if release.package.get("task_input") == CONTRACT:
                    session.add(
                        TaskInput(task_id=row.id, external_task_id=body.external_task_id, rule_name=scheme.name)
                    )
                    session.flush()
                return task_view(session, row)
        except IntegrityError:
            with database.sessions() as session:
                row = session.scalar(select(Task).where(Task.source == source, Task.idempotency_key == key))
                if not row or row.content_hash != content_hash:
                    raise HTTPException(409, "Conflicting task submission") from None
                return task_view(session, row)

    @app.get(public + "/schemes")
    def public_schemes(source: str = source_dep):
        from langflow.business.compiler import runtime_digest
        from langflow.business.maintenance import status

        maintenance = status(database)["status"]
        with database.sessions() as session:
            result = []
            for scheme in session.scalars(select(Scheme).where(Scheme.active_release_id.is_not(None))):
                if source in scheme.allowed_sources:
                    release = session.get(Release, scheme.active_release_id)
                    result.append(
                        {
                            "code": scheme.code,
                            "name": scheme.name,
                            "version": release.version,
                            "parameters": release.package["parameters"],
                            "task_input": release.package.get("task_input"),
                            "external_task_id_required": bool(release.package.get("task_input")),
                            "readiness": "ready"
                            if maintenance == "open" and release.package["runtime_digest"] == runtime_digest()
                            else "unavailable",
                            "maintenance": maintenance,
                            "summary": release.package.get("summary", {}),
                            "schemas": {
                                n["id"]: release.package["schemas"][n["id"]]
                                for n in release.package["graph"]["nodes"]
                                if n["kind"] == "output"
                            },
                        }
                    )
            return result

    @app.post(public + "/tasks", status_code=202)
    def submit(
        body: SubmitTask,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=160)],
        source: str = source_dep,
    ):
        return submit_task(body, source, idempotency_key)

    @app.post(internal + "/tasks", dependencies=dependencies, status_code=202)
    def admin_submit(
        body: SubmitTask, actor: actor_type, idempotency_key: Annotated[str, Header(min_length=1, max_length=160)]
    ):
        return submit_task(body, "admin:" + actor, idempotency_key, actor)

    def query_task(session, task_id, *, actor=None, source=None):
        task = session.get(Task, task_id)
        if not task or (actor and task.owner_id != actor) or (source and task.source != source):
            raise HTTPException(404, "Task not found")
        return task

    def list_tasks(actor=None, source=None, limit=50, offset=0, flow_id=None):
        criteria = [Task.owner_id == actor if actor else Task.source == source]
        if flow_id:
            criteria.extend(
                [
                    Task.scheme_code.in_(select(Scheme.code).where(Scheme.flow_id == flow_id)),
                    Task.id.in_(select(TaskInput.task_id)),
                ]
            )
        with database.sessions() as session:
            return {
                "total": session.scalar(select(func.count()).select_from(Task).where(*criteria)),
                "items": [
                    task_view(session, t)
                    for t in session.scalars(
                        select(Task).where(*criteria).order_by(Task.created_at.desc()).limit(limit).offset(offset)
                    )
                ],
            }

    @app.get(internal + "/tasks", dependencies=dependencies)
    def admin_tasks(
        actor: actor_type,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        flow_id: str | None = None,
    ):
        return list_tasks(actor=actor, limit=limit, offset=offset, flow_id=flow_id)

    @app.get(public + "/tasks")
    def public_tasks(source: str = source_dep, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return list_tasks(source=source, limit=limit, offset=offset)

    def detail(task_id, actor=None, source=None):
        with database.sessions() as session:
            task = query_task(session, task_id, actor=actor, source=source)
            release = session.get(Release, task.release_id)
            assessment = session.get(TaskAssessment, task_id)
            datasets = [
                view(d)
                for d in session.scalars(select(Dataset).where(Dataset.task_id == task_id).order_by(Dataset.created_at))
            ]
            return {
                **task_view(session, task),
                "version": release.version,
                "datasets": datasets,
                "unresolved_rows": sum(
                    d["provenance"].get("blocking_rows", d["row_count"])
                    for d in datasets
                    if d["port"] in {"issues", "unknown"}
                ),
                "classification_counts": {
                    status: sum(
                        d["provenance"].get("classification_counts", {}).get(status, 0)
                        for d in datasets
                        if d["port"] == "issues"
                    )
                    for status in ["continue", "excluded", "uncompared"]
                },
                "coverage_note": "Counts are per node; the same record may appear at multiple stages",
                "assessment": assessment.summary if assessment else {"state": "unassessed", "mode": "unknown"},
            }

    def request_records(task_id, request_id=None, limit=50, offset=0, actor=None, source=None):
        with database.sessions() as session:
            query_task(session, task_id, actor=actor, source=source)
            if request_id:
                receipt = session.get(ExternalRequest, request_id)
                if receipt is None or receipt.task_id != task_id:
                    raise HTTPException(404, "Request not found")
                return view(receipt)
            criteria = ExternalRequest.task_id == task_id
            return {
                "total": session.scalar(select(func.count()).select_from(ExternalRequest).where(criteria)),
                "items": [
                    view(r)
                    for r in session.scalars(
                        select(ExternalRequest)
                        .where(criteria)
                        .order_by(ExternalRequest.created_at, ExternalRequest.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ],
            }

    @app.get(internal + "/result-templates", dependencies=dependencies)
    def result_templates(_actor: actor_type):
        from langflow.business.result_templates import preview

        return [preview()]

    def saved_results(task_id, node_id, limit, offset, *, actor=None, source=None):
        with database.sessions() as session:
            query_task(session, task_id, actor=actor, source=source)
            criteria = [BusinessResult.task_id == task_id]
            if node_id:
                criteria.append(BusinessResult.node_id == node_id)
            items = list(
                session.scalars(
                    select(BusinessResult)
                    .where(*criteria)
                    .order_by(BusinessResult.node_id, BusinessResult.unit_row_id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            return {
                "total": session.scalar(select(func.count()).select_from(BusinessResult).where(*criteria)),
                "items": [view(item) for item in items],
            }

    @app.get(internal + "/tasks/{task_id}/results", dependencies=dependencies)
    def admin_results(
        task_id: str,
        actor: actor_type,
        node_id: str | None = None,
        limit: int = Query(20, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return saved_results(task_id, node_id, limit, offset, actor=actor)

    @app.get(public + "/tasks/{task_id}/results")
    def public_results(
        task_id: str,
        source: str = source_dep,
        node_id: str | None = None,
        limit: int = Query(20, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return saved_results(task_id, node_id, limit, offset, source=source)

    def result_evidence(task_id, result_id, limit, offset, *, actor=None, source=None):
        with database.sessions() as session:
            query_task(session, task_id, actor=actor, source=source)
            result = session.get(BusinessResult, result_id)
            if result is None or result.task_id != task_id:
                raise HTTPException(404, "Result not found")
            criteria = ResultEvidence.result_id == result_id
            return {
                "total": session.scalar(select(func.count()).select_from(ResultEvidence).where(criteria)),
                "items": [
                    view(e)
                    for e in session.scalars(
                        select(ResultEvidence)
                        .where(criteria)
                        .order_by(ResultEvidence.ordinal)
                        .limit(limit)
                        .offset(offset)
                    )
                ],
            }

    @app.get(internal + "/tasks/{task_id}/results/{result_id}/evidence", dependencies=dependencies)
    def admin_result_evidence(
        task_id: str,
        result_id: str,
        actor: actor_type,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return result_evidence(task_id, result_id, limit, offset, actor=actor)

    @app.get(public + "/tasks/{task_id}/results/{result_id}/evidence")
    def public_result_evidence(
        task_id: str,
        result_id: str,
        source: str = source_dep,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return result_evidence(task_id, result_id, limit, offset, source=source)

    def evidence_query(task_id, result_id, *, actor=None, source=None, evidence_id=None, **page):
        from langflow.business.result_evidence import EvidenceView, source_detail

        with database.sessions() as session:
            query_task(session, task_id, actor=actor, source=source)
            result = session.get(BusinessResult, result_id)
            if result is None or result.task_id != task_id:
                raise HTTPException(404, "Result not found")
        try:
            if evidence_id:
                return source_detail(database, task_id, result_id, evidence_id)
            return EvidenceView(database, task_id, result).page(**page)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (OSError, duckdb.Error) as exc:
            raise HTTPException(409, "Saved source snapshot is unavailable") from exc

    evidence_group = Literal["settlement", "study", "series", "image", "recognition", "unlinked"]

    @app.get(internal + "/tasks/{task_id}/results/{result_id}/evidence-view", dependencies=dependencies)
    def admin_evidence_view(
        task_id: str,
        result_id: str,
        actor: actor_type,
        group: evidence_group = "settlement",
        parent: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return evidence_query(task_id, result_id, actor=actor, group=group, parent=parent, limit=limit, offset=offset)

    @app.get(public + "/tasks/{task_id}/results/{result_id}/evidence-view")
    def public_evidence_view(
        task_id: str,
        result_id: str,
        source: str = source_dep,
        group: evidence_group = "settlement",
        parent: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return evidence_query(task_id, result_id, source=source, group=group, parent=parent, limit=limit, offset=offset)

    @app.get(internal + "/tasks/{task_id}/results/{result_id}/evidence/{evidence_id}/detail", dependencies=dependencies)
    def admin_evidence_detail(task_id: str, result_id: str, evidence_id: str, actor: actor_type):
        return evidence_query(task_id, result_id, evidence_id=evidence_id, actor=actor)

    @app.get(public + "/tasks/{task_id}/results/{result_id}/evidence/{evidence_id}/detail")
    def public_evidence_detail(task_id: str, result_id: str, evidence_id: str, source: str = source_dep):
        return evidence_query(task_id, result_id, evidence_id=evidence_id, source=source)

    def result_storage(task_id, node_id, *, actor=None, source=None):
        with database.sessions() as session:
            task = query_task(session, task_id, actor=actor, source=source)
            release = session.get(Release, task.release_id)
            criteria = [BusinessResult.task_id == task_id]
            if node_id:
                criteria.append(BusinessResult.node_id == node_id)
            totals = session.execute(
                select(BusinessResult.complete, BusinessResult.status, func.count())
                .where(*criteria)
                .group_by(BusinessResult.complete, BusinessResult.status)
            ).all()
            assessment = session.get(TaskAssessment, task_id)
            profiles = release.package.get("result_templates", {})
            return {
                "task_status": task.status,
                "release_version": release.version,
                "saved": sum(n for _, _, n in totals),
                "incomplete": sum(n for complete, _, n in totals if not complete),
                "different": sum(n for _, status, n in totals if status == "difference"),
                "assessment": assessment.summary if assessment else None,
                "templates": [
                    {"node_id": key, **value} for key, value in profiles.items() if not node_id or key == node_id
                ],
            }

    @app.get(internal + "/tasks/{task_id}/result-storage", dependencies=dependencies)
    def admin_result_storage(task_id: str, actor: actor_type, node_id: str | None = None):
        return result_storage(task_id, node_id, actor=actor)

    @app.get(public + "/tasks/{task_id}/result-storage")
    def public_result_storage(task_id: str, source: str = source_dep, node_id: str | None = None):
        return result_storage(task_id, node_id, source=source)

    @app.get(internal + "/tasks/{task_id}/requests", dependencies=dependencies)
    def admin_requests(
        task_id: str, actor: actor_type, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
    ):
        return request_records(task_id, limit=limit, offset=offset, actor=actor)

    @app.get(public + "/tasks/{task_id}/requests")
    def public_requests(
        task_id: str, source: str = source_dep, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
    ):
        return request_records(task_id, limit=limit, offset=offset, source=source)

    @app.get(internal + "/tasks/{task_id}/requests/{request_id}", dependencies=dependencies)
    def admin_request(task_id: str, request_id: str, actor: actor_type):
        return request_records(task_id, request_id, actor=actor)

    @app.get(public + "/tasks/{task_id}/requests/{request_id}")
    def public_request(task_id: str, request_id: str, source: str = source_dep):
        return request_records(task_id, request_id, source=source)

    @app.get(internal + "/tasks/{task_id}", dependencies=dependencies)
    def admin_detail(task_id: str, actor: actor_type):
        return detail(task_id, actor=actor)

    @app.get(public + "/tasks/{task_id}")
    def public_detail(task_id: str, source: str = source_dep):
        return detail(task_id, source=source)

    def dataset_page(task_id, dataset_id, limit, offset, actor=None, source=None):
        with database.sessions() as session:
            query_task(session, task_id, actor=actor, source=source)
        try:
            return DatasetStore(database, task_id).page(dataset_id, offset, limit)
        except ValueError as exc:
            raise HTTPException(404, "Dataset not found") from exc

    @app.get(internal + "/tasks/{task_id}/datasets/{dataset_id}", dependencies=dependencies)
    def admin_dataset(
        task_id: str,
        dataset_id: str,
        actor: actor_type,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return dataset_page(task_id, dataset_id, limit, offset, actor=actor)

    @app.get(public + "/tasks/{task_id}/datasets/{dataset_id}")
    def public_dataset(
        task_id: str,
        dataset_id: str,
        source: str = source_dep,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return dataset_page(task_id, dataset_id, limit, offset, source=source)

    @app.get(internal + "/tasks/{task_id}/execution", dependencies=dependencies)
    def execution(task_id: str, actor: actor_type):
        with database.sessions() as session:
            task = query_task(session, task_id, actor=actor)
            return {**view(task), "package": session.get(Release, task.release_id).package}
