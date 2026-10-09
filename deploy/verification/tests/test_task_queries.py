from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from conftest import ACTOR, INTERNAL_TOKEN
from fastapi import FastAPI
from langflow.verification.database import Task
from test_api_pipeline import BASE, execute, submit

ADMIN = {"Authorization": f"Bearer {INTERNAL_TOKEN}", "X-Verification-Actor": ACTOR}
OTHER_SOURCE = {"Authorization": "Bearer other-client-token-123456"}


@pytest.mark.parametrize("suffix", ["", "/task", "/task/runs", "/task/results", "/task/evidence"])
async def test_platform_task_facade_requires_admin_and_forwards_authenticated_actor(monkeypatch, suffix):
    from langflow.api.utils.core import get_current_active_user
    from langflow.api.v1 import verification

    actor = SimpleNamespace(id=uuid4(), is_superuser=False)
    platform = FastAPI()
    platform.include_router(verification.router, prefix="/api/v1")
    platform.dependency_overrides[get_current_active_user] = lambda: actor
    forwarded = []

    async def business(method, path, **kwargs):
        forwarded.append((method, path, kwargs))
        return {"ok": True}

    monkeypatch.setattr(verification, "business", business)
    task_id = str(uuid4())
    path = BASE + "/tasks" + suffix.replace("task", task_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=platform), base_url="http://platform") as http:
        assert (await http.get(path)).status_code == 403
        assert not forwarded
        actor.is_superuser = True
        assert (await http.get(path, headers={"X-Verification-Actor": str(uuid4())})).status_code == 200
        assert forwarded[-1][2]["actor"] is actor


async def test_task_list_is_paginated_filterable_and_source_scoped(client, database):
    first = await submit(client, "first-query-task")
    second = await submit(client, "second-query-task")
    with database.sessions.begin() as session:
        session.get(Task, second["task_id"]).source_system = "other-regulator"

    response = await client.get(BASE + "/tasks", params={"limit": 1})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["task_id"] == first["task_id"]
    assert (await client.get(BASE + "/tasks", params={"offset": 1})).json()["items"] == []
    assert (await client.get(BASE + "/tasks", params={"q": "first-query"})).json()["total"] == 1
    assert (await client.get(BASE + "/tasks", params={"q": "常州市"})).json()["total"] == 1
    assert (await client.get(BASE + "/tasks", params={"status": "completed"})).json()["total"] == 0
    assert (await client.get(BASE + "/tasks", params={"status": "invalid"})).status_code == 422
    assert (await client.get(BASE + "/tasks", params={"limit": 201})).status_code == 422
    other = (await client.get(BASE + "/tasks", headers=OTHER_SOURCE)).json()
    assert other["total"] == 1 and other["items"][0]["task_id"] == second["task_id"]
    admin_page = (await client.get(BASE + "/internal/tasks", headers=ADMIN, params={"limit": 1})).json()
    assert admin_page["total"] == 2 and len(admin_page["items"]) == 1
    hidden = await client.get(BASE + "/internal/tasks", headers={**ADMIN, "X-Verification-Actor": str(uuid4())})
    assert hidden.json()["total"] == 0


@pytest.mark.parametrize("suffix", ["", "/runs", "/results", "/evidence"])
async def test_admin_task_reads_require_service_auth_and_rule_ownership(client, suffix):
    accepted = await submit(client)
    url = BASE + f"/internal/tasks/{accepted['task_id']}" + suffix
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={**ADMIN, "X-Verification-Actor": str(uuid4())})).status_code == 404
    assert (await client.get(url, headers=ADMIN)).status_code == 200


async def test_results_and_evidence_are_readonly_paginated_and_pinned_to_run(client, database, settings, transport):
    accepted = await submit(client)
    await execute(database, settings, transport, accepted)
    internal = BASE + f"/internal/tasks/{accepted['task_id']}"
    calls = len(transport.requests)
    before = (await client.get(internal + "/results", headers=ADMIN, params={"limit": 1})).json()
    assert before["result"]["summary"]["units"] == 2
    assert len(before["result"]["results"]) == 1
    next_page = (await client.get(internal + "/results", headers=ADMIN, params={"limit": 1, "offset": 1})).json()
    assert next_page["result"]["results"][0]["category"] != before["result"]["results"][0]["category"]
    evidence = (await client.get(internal + "/evidence", headers=ADMIN, params={"limit": 1})).json()
    assert len(evidence["artifacts"]) == len(evidence["model_requests"]) == 1
    assert evidence["pagination"]["artifacts_total"] > 1
    assert evidence["pagination"]["model_requests_total"] == 2
    assert len(transport.requests) == calls

    rerun = await client.post(
        BASE + f"/tasks/{accepted['task_id']}/runs",
        json={"confirmed_execution_ended": True, "reason": "Inspect previous result while next run waits"},
    )
    assert rerun.status_code == 202
    current = (await client.get(internal + "/results", headers=ADMIN)).json()
    assert current["status"] == "waiting" and current["result"] is None
    history = (await client.get(internal + "/runs", headers=ADMIN)).json()
    assert len(history) == 2
    pinned = (await client.get(internal + "/results", headers=ADMIN, params={"run_id": accepted["run_id"]})).json()
    assert pinned["status"] == "completed" and pinned["result_id"] == before["result_id"]
    assert (await client.get(internal + "/results", headers=ADMIN, params={"run_id": str(uuid4())})).status_code == 404
    for suffix in ["", "/runs", "/results", "/evidence"]:
        assert (
            await client.get(BASE + f"/tasks/{accepted['task_id']}" + suffix, headers=OTHER_SOURCE)
        ).status_code == 404
