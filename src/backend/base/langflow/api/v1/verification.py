"""Langflow administrator surface for verification drafts, immutable releases and runs."""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser
from langflow.services.auth.utils import api_key_security
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import UserRead
from langflow.services.deps import get_background_execution_service, session_scope
from langflow.verification.execution import submit_execution
from langflow.verification.schemas import (
    ActivateRelease,
    PrepareRelease,
    PublishRelease,
    RuleCreate,
    RunStatus,
    SaveRuleDraft,
)
from langflow.verification.settings import FlowSettings

router = APIRouter(prefix="/verification", tags=["Verification"])


def admin(user):
    if not user.is_superuser:
        raise HTTPException(403, "规则管理需要平台管理员身份")


async def business(method, path, *, actor=None, payload=None, params=None):
    settings = FlowSettings()
    headers = {"Authorization": f"Bearer {settings.internal_token.get_secret_value()}"}
    if actor:
        headers["X-Verification-Actor"] = str(actor.id)
    async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
        try:
            response = await client.request(
                method,
                settings.api_url + "/api/v1/verification/internal" + path,
                headers=headers,
                json=payload,
                params=params,
            )
        except httpx.TransportError as exc:
            raise HTTPException(503, "核验业务服务暂不可用") from exc
    if not response.is_success:
        try:
            detail = response.json().get("detail", "核验请求失败")
        except ValueError:
            detail = "核验请求失败"
        raise HTTPException(response.status_code, detail)
    return response.json()


async def owned_flow(flow_id, user):
    async with session_scope() as session:
        flow = (await session.exec(select(Flow).where(Flow.id == UUID(str(flow_id)), Flow.user_id == user.id))).first()
        if flow is None:
            raise HTTPException(404, "草稿流程不存在")
        return flow.data


@router.get("/rules")
async def rules(user: CurrentActiveUser):
    admin(user)
    return await business("GET", "/rules", actor=user)


@router.post("/rules", status_code=201)
async def create_rule(body: RuleCreate, user: CurrentActiveUser):
    admin(user)
    await owned_flow(body.flow_id, user)
    return await business("POST", "/rules", actor=user, payload=body.model_dump(mode="json"))


@router.put("/rules/{code}/draft")
async def save_draft(code: str, body: SaveRuleDraft, user: CurrentActiveUser):
    admin(user)
    return await business("PUT", f"/rules/{code}/draft", actor=user, payload=body.model_dump(mode="json"))


@router.post("/rules/{code}/candidates", status_code=201)
async def prepare(code: str, body: PrepareRelease, user: CurrentActiveUser):
    admin(user)
    rules = await business("GET", "/rules", actor=user)
    rule = next((r for r in rules if r["code"] == code), None)
    if rule is None:
        raise HTTPException(404, "规则不存在")
    graph = await owned_flow(rule["flow_id"], user)
    return await business(
        "POST", f"/rules/{code}/candidates", actor=user, payload={**body.model_dump(mode="json"), "graph": graph}
    )


@router.post("/rules/{code}/releases", status_code=201)
async def publish(code: str, body: PublishRelease, user: CurrentActiveUser):
    admin(user)
    return await business("POST", f"/rules/{code}/releases", actor=user, payload=body.model_dump(mode="json"))


@router.get("/rules/{code}/releases")
async def releases(code: str, user: CurrentActiveUser):
    admin(user)
    return await business("GET", f"/rules/{code}/releases", actor=user)


@router.get("/rules/{code}/releases/{release_id}")
async def read_release(code: str, release_id: UUID, user: CurrentActiveUser):
    admin(user)
    return await business("GET", f"/rules/{code}/releases/{release_id}", actor=user)


@router.put("/rules/{code}/active")
async def activate(code: str, body: ActivateRelease, user: CurrentActiveUser):
    admin(user)
    return await business("PUT", f"/rules/{code}/active", actor=user, payload=body.model_dump(mode="json"))


@router.get("/rules/{code}/audit")
async def audit(code: str, user: CurrentActiveUser):
    admin(user)
    return await business("GET", f"/rules/{code}/audit", actor=user)


WorkerUser = Annotated[UserRead, Depends(api_key_security)]


@router.get("/tasks")
async def task_list(
    user: CurrentActiveUser,
    status: RunStatus | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    admin(user)
    params: dict[str, str | int] = {"q": q, "limit": limit, "offset": offset}
    if status:
        params["status"] = status
    return await business("GET", "/tasks", actor=user, params=params)


@router.get("/tasks/{task_id}")
async def task_detail(task_id: UUID, user: CurrentActiveUser, run_id: UUID | None = None):
    admin(user)
    return await business("GET", f"/tasks/{task_id}", actor=user, params={"run_id": str(run_id)} if run_id else None)


@router.get("/tasks/{task_id}/runs")
async def task_runs(
    task_id: UUID,
    user: CurrentActiveUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    admin(user)
    return await business("GET", f"/tasks/{task_id}/runs", actor=user, params={"limit": limit, "offset": offset})


@router.get("/tasks/{task_id}/results")
async def task_results(
    task_id: UUID,
    user: CurrentActiveUser,
    run_id: UUID | None = None,
    version: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    admin(user)
    params: dict[str, str | int] = {"version": version, "limit": limit, "offset": offset}
    if run_id:
        params["run_id"] = str(run_id)
    return await business("GET", f"/tasks/{task_id}/results", actor=user, params=params)


@router.get("/tasks/{task_id}/evidence")
async def task_evidence(
    task_id: UUID,
    user: CurrentActiveUser,
    run_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    admin(user)
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if run_id:
        params["run_id"] = str(run_id)
    return await business("GET", f"/tasks/{task_id}/evidence", actor=user, params=params)


@router.post("/runs/{run_id}/execute", status_code=202)
async def execute(run_id: UUID, user: WorkerUser):
    admin(user)
    execution = await business("GET", f"/runs/{run_id}/execution")
    if execution["package"]["owner_id"] != str(user.id):
        raise HTTPException(403, "发布规则不属于该执行账号")
    return await submit_execution(execution, user)


@router.get("/runs/{run_id}/job")
async def job_status(run_id: UUID, user: WorkerUser):
    admin(user)
    execution = await business("GET", f"/runs/{run_id}/execution")
    if execution["package"]["owner_id"] != str(user.id):
        raise HTTPException(403, "发布规则不属于该执行账号")
    from langflow.services.deps import get_job_service

    job = await get_job_service().get_job_by_job_id(UUID(execution["job_id"]))
    if job is None:
        return {"job_id": execution["job_id"], "status": "not_registered"}
    return await get_background_execution_service().status(UUID(execution["job_id"]), user)
