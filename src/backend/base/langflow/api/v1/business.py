"""Authenticated management of generic business workflows and datasets."""

from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from langflow.api.utils import CurrentActiveUser
from langflow.api.v1.verification import admin, owned_flow
from langflow.services.auth.utils import api_key_security
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import UserRead
from langflow.services.deps import session_scope
from langflow.verification.settings import FlowSettings

router = APIRouter(prefix="/business", tags=["Business workflows"])


async def proxy(method, path, user, *, payload=None, params=None, key=None, files=None):
    settings = FlowSettings()
    headers = {
        "Authorization": "Bearer " + settings.internal_token.get_secret_value(),
        "X-Business-Actor": str(user.id),
    }
    if key:
        headers["Idempotency-Key"] = key
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as http:
        try:
            response = await http.request(
                method,
                settings.api_url + "/api/v1/business/internal/" + path,
                headers=headers,
                params=params,
                **({"files": files} if files else {"json": payload}),
            )
        except httpx.TransportError as exc:
            raise HTTPException(503, "Business service is unavailable") from exc
    if not response.is_success:
        try:
            detail = response.json().get("detail", "Business request failed")
        except ValueError:
            detail = "Business request failed"
        raise HTTPException(response.status_code, detail)
    return response.json()


@router.get("/templates")
async def templates(user: CurrentActiveUser):
    admin(user)
    from langflow.business.templates import templates

    return templates()


@router.post("/schemes", status_code=201)
async def create_scheme(body: dict, user: CurrentActiveUser):
    admin(user)
    from langflow.business.components import to_langflow
    from langflow.business.contracts import Graph

    graph = Graph.model_validate(body["graph"]).model_dump()
    data = to_langflow(graph, body["name"])
    flow_id = uuid4()
    async with session_scope() as session:
        flow = Flow(id=flow_id, name=body["name"], data=data, user_id=user.id)
        session.add(flow)
        await session.commit()
    try:
        return await proxy(
            "POST",
            "schemes",
            user,
            payload={
                "code": body["code"],
                "name": body["name"],
                "flow_id": str(flow_id),
                "graph": graph,
                "allowed_sources": body.get("allowed_sources", []),
            },
        )
    except BaseException:
        async with session_scope() as session:
            flow = await session.get(Flow, flow_id)
            if flow:
                await session.delete(flow)
                await session.commit()
        raise


@router.post("/schemes/{code}/releases", status_code=201)
async def publish(code: str, body: dict, user: CurrentActiveUser):
    admin(user)
    schemes = await proxy("GET", "schemes", user)
    scheme = next((s for s in schemes if s["code"] == code), None)
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    from langflow.business.components import from_langflow

    graph = from_langflow(await owned_flow(scheme["flow_id"], user))
    if graph != scheme["draft"]:
        scheme = await proxy(
            "PUT",
            f"schemes/{code}/draft",
            user,
            payload={"graph": graph, "expected_revision": body["expected_revision"]},
        )
    return await proxy(
        "POST",
        f"schemes/{code}/releases",
        user,
        payload={"expected_revision": scheme["revision"], "note": body.get("note", "")},
    )


@router.post("/inspect")
async def inspect(body: dict, user: CurrentActiveUser):
    admin(user)
    from langflow.business.components import from_langflow

    graph = from_langflow(body["canvas"]) if "canvas" in body else body["graph"]
    return await proxy("POST", "inspect", user, payload={"graph": graph})


@router.post("/files")
async def upload(user: CurrentActiveUser, file: Annotated[UploadFile, File()]):
    admin(user)
    return await proxy("POST", "files", user, files={"file": (file.filename, file.file, file.content_type)})


WorkerUser = Annotated[UserRead, Depends(api_key_security)]


@router.post("/tasks/{task_id}/execute")
async def execute(task_id: UUID, user: WorkerUser):
    admin(user)
    from langflow.business.execution import submit_execution

    return await submit_execution(str(task_id), user)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
async def management(path: str, request: Request, user: CurrentActiveUser):
    admin(user)
    # Explicit management surface; service-only execution paths are not proxied.
    if path.endswith("/execution") or (
        path not in {"catalog", "connections", "schemes", "tasks", "maintenance", "result-templates"}
        and not path.startswith(("connections/", "schemes/", "tasks/"))
    ):
        raise HTTPException(404, "Not found")
    body = await request.json() if request.method != "GET" else None
    return await proxy(
        request.method,
        path,
        user,
        payload=body,
        params=dict(request.query_params),
        key=request.headers.get("Idempotency-Key"),
    )
