import httpx
import pytest
from conftest import INTERNAL_TOKEN, ServiceTransport, draft_graph, seed_release
from langflow.verification.database import (
    ModelRequest,
    Result,
    ReviewRecord,
    VerificationUnit,
)
from langflow.verification.demo import create_demo_app, example_task
from langflow.verification.pipeline import ExecutionUncertain, Pipeline
from sqlalchemy import select

BASE = "/api/v1/verification"
INTERNAL = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}


async def submit(client, reference="demo-001", body=None):
    response = await client.post(BASE + "/tasks", json=body or example_task(), headers={"Idempotency-Key": reference})
    assert response.status_code == 202, response.text
    return response.json()


async def execute(database, settings, transport, accepted, through=8):
    assert database.claim() == accepted["run_id"]
    async with httpx.AsyncClient(transport=transport) as http:
        pipeline = Pipeline(settings, http)
        await pipeline.internal("POST", accepted["run_id"], "/execution/start")
        context = {key: accepted[key] for key in ("task_id", "run_id", "release_id", "job_id")}
        for stage in range(through + 1):
            context = await pipeline.execute(f"{stage:02d}", context)
            assert "settlements" not in context and "groups" not in context
    return context


async def test_dedup_conflict_and_source_isolation(client, database, settings):
    first = await submit(client)
    seed_release(database, settings)
    assert (await submit(client))["release_id"] == first["release_id"]
    second = await submit(client, "second")
    assert second["release_id"] != first["release_id"]
    body = {**example_task(), "rule": "other"}
    assert (await client.post(BASE + "/tasks", json=body, headers={"Idempotency-Key": "demo-001"})).status_code == 409
    assert (
        await client.get(
            BASE + f"/tasks/{first['task_id']}", headers={"Authorization": "Bearer other-client-token-123456"}
        )
    ).status_code == 404
    assert (await client.get(BASE + f"/internal/runs/{first['run_id']}")).status_code == 401


async def test_full_pipeline_cross_page_grouping_and_readonly_queries(client, settings, database, transport):
    accepted = await submit(client)
    context = await execute(database, settings, transport, accepted)
    assert context["receipt"]["saved"]
    response = (await client.get(BASE + f"/tasks/{accepted['task_id']}/results")).json()
    assert response["available"] and response["status"] == "completed"
    summary = response["result"]["summary"]
    assert summary["details"] == 3 and summary["units"] == 2 and summary["difference"] == 1
    hip = next(r for r in response["result"]["results"] if "detail-hip" in r["detail_ids"])
    assert len(hip["detail_ids"]) == 2 and hip["fee"]["delta"] == "-10000.00"
    assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 2
    assert len([r for r in transport.requests if r[2] == "/v1/settlements/query"]) == 3
    await client.get(BASE + f"/tasks/{accepted['task_id']}/results")
    assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 2
    repeated = await client.post(BASE + f"/internal/runs/{accepted['run_id']}/results", headers=INTERNAL)
    assert repeated.json()["result_id"] == context["receipt"]["result_id"]
    restarted = await client.post(BASE + f"/internal/runs/{accepted['run_id']}/execution/start", headers=INTERNAL)
    assert restarted.status_code == 409


async def test_rerun_uses_original_release_and_sealed_data(client, settings, database, transport):
    first = await submit(client)
    await execute(database, settings, transport, first)
    seed_release(database, settings)
    response = await client.post(
        BASE + f"/tasks/{first['task_id']}/runs",
        json={"confirmed_execution_ended": True, "reason": "Confirmed old execution ended"},
    )
    assert response.status_code == 202
    second = response.json()
    assert second["release_id"] == first["release_id"] and second["job_id"] != first["job_id"]
    await execute(database, settings, transport, second)
    assert len([r for r in transport.requests if r[2] == "/v1/settlements/query"]) == 3
    with database.sessions() as session:
        assert len(list(session.scalars(select(Result)))) == 2
        assert len(list(session.scalars(select(ModelRequest)))) == 4
    late = await client.post(
        BASE + f"/internal/runs/{first['run_id']}/artifacts",
        headers=INTERNAL,
        json={"kind": "comparison", "payload": {}},
    )
    assert late.status_code == 409


async def test_pinned_rule_changes_do_not_leak(client, settings, database, transport):
    first = await submit(client)
    graph = draft_graph()
    for n in graph["nodes"]:
        if "VerificationResultComparison@" in n["data"]["type"]:
            n["data"]["node"]["template"]["comparisons"]["value"] = ["种类"]
    seed_release(database, settings, graph)
    second = await submit(client, "v2")
    await execute(database, settings, transport, first)
    await execute(database, settings, transport, second)
    values = []
    for task in [first, second]:
        data = (await client.get(BASE + f"/tasks/{task['task_id']}/results")).json()["result"]["results"]
        values.append(next(r for r in data if "detail-hip" in r["detail_ids"])["conclusion"])
    assert values == ["difference", "consistent"]


@pytest.mark.parametrize("fault_kind", ["timeout", "malformed", "no_images", "partial", "save_failed"])
async def test_failures_never_invent_zero_or_completion(client, settings, database, app, fault_kind):
    def fault(request):
        if request.url.path == "/v1/recognitions":
            if fault_kind == "timeout":
                raise httpx.ReadTimeout("test", request=request)
            if fault_kind == "malformed":
                return httpx.Response(200, json={"count": "not a result"})
            if fault_kind == "partial":
                return httpx.Response(200, json={"status": "partial_failed", "simulated": True})
        if fault_kind == "no_images" and request.url.path.endswith("/sop-instance-uid"):
            return httpx.Response(200, json={"code": 200, "data": [], "simulated": True})
        if fault_kind == "save_failed" and request.url.path.endswith("/results"):
            return httpx.Response(503, json={"detail": "unavailable"})
        return None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    task = await submit(client)
    if fault_kind in {"timeout", "malformed", "save_failed"}:
        with pytest.raises((ExecutionUncertain, httpx.HTTPError)):
            await execute(database, settings, transport, task)
    else:
        await execute(database, settings, transport, task)
    result = (await client.get(BASE + f"/tasks/{task['task_id']}/results")).json()
    if fault_kind in {"timeout", "malformed"}:
        assert result["status"] == "needs_confirmation" and not result["available"]
        assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 1
    elif fault_kind == "save_failed":
        assert result["status"] != "completed" and not result["available"]
    else:
        assert all(r["conclusion"] == "not_compared" for r in result["result"]["results"])


async def test_missing_facts_do_not_become_rule_booleans(client, settings, database, transport):
    with database.sessions.begin() as session:
        for record in session.scalars(select(ReviewRecord)):
            record.payload = {**record.payload, "counting_validated": False}
    task = await submit(client)
    await execute(database, settings, transport, task)
    result = (await client.get(BASE + f"/tasks/{task['task_id']}/results")).json()
    assert all(r["quantity"]["status"] == "not_compared" for r in result["result"]["results"])


@pytest.mark.parametrize("kind", ["empty", "outside", "missing_time", "conflict", "repeat_cursor", "page_failed"])
async def test_range_integrity(client, settings, database, app, kind):
    from langflow.verification.demo import settlement_fixture

    calls = 0

    def fault(request):
        nonlocal calls
        if request.url.path != "/v1/settlements/query":
            return None
        calls += 1
        if kind == "empty":
            items = []
        else:
            row = settlement_fixture("hip")
            if kind == "outside":
                row["settlement_time"] = "2025-09-01T00:00:00+08:00"
            if kind == "missing_time":
                row["settlement_time"] = None
            if kind == "conflict" and calls > 1:
                row["quantity"] = "99"
            items = [row]
        if kind == "page_failed" and calls > 1:
            return httpx.Response(503)
        cursor = "1" if kind in {"conflict", "repeat_cursor", "page_failed"} else None
        return httpx.Response(
            200,
            json={
                "items": items,
                "simulated": True,
                "snapshot_token": "test",
                "next_cursor": cursor,
                "consistency": "observed_pages",
            },
        )

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    task = await submit(client)
    if kind == "empty":
        await execute(database, settings, transport, task)
        result = (await client.get(BASE + f"/tasks/{task['task_id']}/results")).json()
        assert result["result"]["summary"]["empty"] and result["result"]["results"] == []
    else:
        with pytest.raises((ValueError, httpx.HTTPError)):
            await execute(database, settings, transport, task)
        result = (await client.get(BASE + f"/tasks/{task['task_id']}/results")).json()
        assert not result["available"] and result["status"] == "failed"


async def test_incomplete_coverage_prevents_finish(client, settings, database, transport):
    task = await submit(client)
    ctx = await execute(database, settings, transport, task, through=7)
    with database.sessions.begin() as session:
        unit = session.scalar(select(VerificationUnit))
        unit.stage = "06"
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await Pipeline(settings, http).execute("08", ctx)
    with database.sessions() as session:
        assert session.scalar(select(Result)) is None
