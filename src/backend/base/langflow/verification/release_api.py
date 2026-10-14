# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Internal management endpoints reached through the authenticated Langflow admin facade."""

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from langflow.verification.database import (
    ActivationAudit,
    ReleaseCandidate,
    RuleDefinition,
    RuleRelease,
    Run,
    Task,
    fingerprint,
)
from langflow.verification.releases import activate, compile_release, publish, release_view, rule_view
from langflow.verification.schemas import ActivateRelease, PrepareRelease, PublishRelease, RuleCreate, SaveRuleDraft


class CandidateWrite(PrepareRelease):
    graph: dict


def register_release_routes(app, database, settings, dependencies):
    from langflow.verification.api import active_run, conflict

    prefix = "/api/v1/verification/internal"
    from langflow.business.migration import require_legacy_intake
    def require_writable():
        with database.sessions() as session:
            require_legacy_intake(session)

    from fastapi import Depends
    writes = [*dependencies, Depends(require_writable)]
    actor_type = Annotated[str, Header(alias="X-Verification-Actor", min_length=1, max_length=36)]

    def owned(session, code, actor):
        rule = session.scalar(
            select(RuleDefinition)
            .where(RuleDefinition.code == code, RuleDefinition.owner_id == actor)
            .with_for_update()
        )
        if rule is None:
            raise HTTPException(404, "规则不存在")
        return rule

    @app.get(prefix + "/rules", dependencies=dependencies)
    def rules(actor: actor_type):
        with database.sessions() as session:
            return [
                rule_view(session, rule)
                for rule in session.scalars(
                    select(RuleDefinition).where(RuleDefinition.owner_id == actor).order_by(RuleDefinition.name)
                )
            ]

    @app.post(prefix + "/rules", dependencies=writes, status_code=201)
    def create(body: RuleCreate, actor: actor_type):
        try:
            with database.sessions.begin() as session:
                # Names and codes share a selection namespace; don't allow cross-column aliases.
                if session.scalar(
                    select(RuleDefinition).where(
                        RuleDefinition.code.in_([body.code, body.name])
                        | RuleDefinition.name.in_([body.code, body.name])
                    )
                ):
                    conflict("规则编码或名称已存在")
                rule = RuleDefinition(code=body.code, name=body.name, flow_id=str(body.flow_id), owner_id=actor)
                session.add(rule)
                session.flush()
                return rule_view(session, rule)
        except IntegrityError as exc:
            raise HTTPException(409, "规则编码或名称已存在") from exc

    @app.put(prefix + "/rules/{code}/draft", dependencies=writes)
    def save_draft(code: str, body: SaveRuleDraft, actor: actor_type):
        with database.sessions.begin() as session:
            rule = owned(session, code, actor)
            updated = session.execute(
                update(RuleDefinition)
                .where(RuleDefinition.code == code, RuleDefinition.draft_revision == body.expected_revision)
                .values(
                    draft_config=body.model_dump(exclude={"expected_revision"}, mode="json"),
                    draft_revision=body.expected_revision + 1,
                )
            )
            if updated.rowcount != 1:
                conflict("规则草稿已被修改，请刷新后重试")
            session.refresh(rule)
            return rule_view(session, rule)

    @app.post(prefix + "/rules/{code}/candidates", dependencies=writes, status_code=201)
    async def prepare(code: str, body: CandidateWrite, actor: actor_type):
        with database.sessions() as session:
            rule = owned(session, code, actor)
            flow_id = rule.flow_id
        try:
            package = compile_release(body.graph, body.catalog_mapping, settings, flow_id=flow_id, owner_id=actor)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        from langflow.verification.validation import validate_candidate

        try:
            validation = await validate_candidate(package, settings)
        except Exception as exc:
            raise HTTPException(422, f"候选模拟验证未完成：{type(exc).__name__}。请检查节点与接口契约。") from exc
        with database.sessions.begin() as session:
            owned(session, code, actor)
            candidate = ReleaseCandidate(
                rule_code=code,
                content_hash=fingerprint(package),
                package=package,
                author_id=actor,
                validation=validation,
                note=body.note,
            )
            session.add(candidate)
            session.flush()
            return {
                "id": candidate.id,
                "content_hash": candidate.content_hash,
                "validation": validation,
                "configurations": package["configurations"],
            }

    @app.post(prefix + "/rules/{code}/releases", dependencies=writes, status_code=201)
    def release(code: str, body: PublishRelease, actor: actor_type):
        try:
            with database.sessions.begin() as session:
                return release_view(publish(session, owned(session, code, actor), body, actor))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get(prefix + "/rules/{code}/releases", dependencies=dependencies)
    def history(code: str, actor: actor_type):
        with database.sessions() as session:
            owned(session, code, actor)
            return [
                release_view(r)
                for r in session.scalars(
                    select(RuleRelease).where(RuleRelease.rule_code == code).order_by(RuleRelease.version.desc())
                )
            ]

    @app.get(prefix + "/rules/{code}/releases/{release_id}", dependencies=dependencies)
    def read_release(code: str, release_id: UUID, actor: actor_type):
        with database.sessions() as session:
            owned(session, code, actor)
            release = session.get(RuleRelease, str(release_id))
            if release is None or release.rule_code != code:
                raise HTTPException(404, "发布版本不存在")
            return release_view(release, include_package=True)

    @app.put(prefix + "/rules/{code}/active", dependencies=writes)
    def enable(code: str, body: ActivateRelease, actor: actor_type):
        try:
            with database.sessions.begin() as session:
                return activate(session, owned(session, code, actor), body, actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get(prefix + "/rules/{code}/audit", dependencies=dependencies)
    def audit(code: str, actor: actor_type):
        with database.sessions() as session:
            owned(session, code, actor)
            return [
                {
                    "revision": a.revision,
                    "release_id": a.release_id,
                    "author_id": a.author_id,
                    "created_at": a.created_at,
                }
                for a in session.scalars(
                    select(ActivationAudit).where(ActivationAudit.rule_code == code).order_by(ActivationAudit.revision)
                )
            ]

    @app.get(prefix + "/runs/{run_id}/execution", dependencies=dependencies)
    def execution(run_id: UUID):
        with database.sessions() as session:
            run = session.get(Run, str(run_id))
            if run is None:
                raise HTTPException(404, "Run not found")
            release = session.get(RuleRelease, run.release_id)
            task = session.get(Task, run.task_id)
            return {
                "run_id": run.id,
                "task_id": task.id,
                "current_run_id": task.current_run_id,
                "job_id": run.job_id,
                "release_id": release.id,
                "package": release.package,
                "content_hash": release.content_hash,
                "status": run.status,
                "execution_started": run.execution_started,
            }

    @app.post(prefix + "/runs/{run_id}/execution/start", dependencies=dependencies)
    def start_execution(run_id: UUID):
        with database.sessions.begin() as session:
            run = active_run(session, str(run_id))
            changed = session.execute(
                update(Run).where(Run.id == run.id, Run.execution_started.is_(False)).values(execution_started=True)
            )
            if changed.rowcount != 1:
                conflict("This Run has already started; execution cannot be repeated")
            return {"saved": True, "job_id": run.job_id}
