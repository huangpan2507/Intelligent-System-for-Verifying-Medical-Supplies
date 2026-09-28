import json

import httpx
import pytest
from conftest import INTERNAL_TOKEN, ServiceTransport
from fastapi import FastAPI
from langflow.verification.database import ModelRequest, Result, Run
from langflow.verification.demo import create_demo_app, example_task
from langflow.verification.pipeline import ExecutionUncertain, Pipeline
from langflow.verification.worker import run_once
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

BASE = "/api/v1/verification"


async def submit(client, reference="demo-001"):
    response = await client.post(BASE + "/tasks", json=example_task(reference))
    assert response.status_code == 202, response.text
    return response.json()


async def execute(database, settings, transport, accepted):
    assert database.claim() == accepted["run_id"]
    async with httpx.AsyncClient(transport=transport) as http:
        pipeline = Pipeline(settings, http)
        context = {key: accepted[key] for key in ("task_id", "run_id", "detail_ids")}
        for stage in range(9):
            context = await pipeline.execute(f"{stage:02d}", context)
    return context


async def test_dedup_conflict_and_source_isolation(client, database):
    accepted = await submit(client)
    assert (await submit(client))["run_id"] == accepted["run_id"]
    body = example_task()
    body["detail_ids"].reverse()
    assert (await client.post(BASE + "/tasks", json=body)).json()["task_id"] == accepted["task_id"]
    body["config"]["days_before"] = 3
    assert (await client.post(BASE + "/tasks", json=body)).status_code == 409
    assert (await client.get(BASE + "/tasks/by-reference/demo-001")).json()["task_id"] == accepted["task_id"]
    assert (
        await client.get(
            BASE + f"/tasks/{accepted['task_id']}", headers={"Authorization": "Bearer other-client-token-123456"}
        )
    ).status_code == 404
    assert (await client.get(BASE + f"/internal/runs/{accepted['run_id']}")).status_code == 401
    assert database.claim() == accepted["run_id"]
    assert database.claim() is None


async def test_full_pipeline_persistence_and_queries_are_read_only(client, settings, database, transport):
    accepted = await submit(client)
    context = await execute(database, settings, transport, accepted)
    assert context["receipt"]["saved"] is True
    response = await client.get(BASE + f"/tasks/{accepted['task_id']}/results")
    data = response.json()
    assert data["available"] and data["status"] == "completed" and data["result"]["simulated"]
    hip, knee = data["result"]["results"]
    assert hip["fee"]["delta"] == "-10000.00"
    assert knee["conclusion"] == "consistent"
    assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 2
    await client.get(BASE + f"/tasks/{accepted['task_id']}/results")
    assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 2
    evidence = (await client.get(BASE + f"/tasks/{accepted['task_id']}/evidence")).json()
    assert len(evidence["model_requests"]) == 2
    assert {a["kind"] for a in evidence["artifacts"]} == {
        "settlement_snapshot",
        "selection",
        "studies",
        "screening",
        "manifest",
        "comparison",
    }
    assert all(r["raw_response"]["simulated"] for r in evidence["model_requests"])


async def test_rerun_keeps_history_and_new_requests(client, settings, database, transport):
    first = await submit(client)
    first_context = await execute(database, settings, transport, first)
    body = {"confirmed_execution_ended": True, "reason": "Operator confirmed the old execution has ended"}
    assert (await client.post(BASE + f"/tasks/{first['task_id']}/runs", json={})).status_code == 422
    second = (await client.post(BASE + f"/tasks/{first['task_id']}/runs", json=body)).json()
    assert second["run_id"] != first["run_id"]
    await execute(database, settings, transport, second)
    first_result = (
        await client.get(BASE + f"/tasks/{first['task_id']}/results", params={"run_id": first["run_id"]})
    ).json()
    assert first_result["result"] == first_context["result"]
    with database.sessions() as session:
        requests = list(session.scalars(select(ModelRequest)))
        assert len({r.id for r in requests}) == 4
        assert len(list(session.scalars(select(Result)))) == 2
    late = await client.post(
        BASE + f"/internal/runs/{first['run_id']}/artifacts",
        headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
        json={"kind": "comparison", "payload": {}},
    )
    assert late.status_code == 409


async def test_model_timeout_is_not_retried_and_requires_confirmation(client, settings, database, app):
    def fault(request):
        if request.url.path == "/v1/recognitions":
            # Registration has already committed when the model receives a request.
            with database.sessions() as session:
                assert session.scalar(select(ModelRequest)).status == "registered"
            raise httpx.ReadTimeout("inference accepted, response lost")

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    with pytest.raises(ExecutionUncertain):
        await execute(database, settings, transport, accepted)
    assert database.claim() is None
    state = (await client.get(BASE + f"/tasks/{accepted['task_id']}")).json()
    assert state["status"] == "needs_confirmation"
    body = {"confirmed_execution_ended": True, "reason": "Operator contacted the model service"}
    assert (await client.post(BASE + f"/tasks/{accepted['task_id']}/runs", json=body)).status_code == 409
    confirmed = await client.post(
        BASE + f"/tasks/{accepted['task_id']}/runs/{accepted['run_id']}/confirmation", json=body
    )
    assert confirmed.status_code == 200
    rerun = await client.post(BASE + f"/tasks/{accepted['task_id']}/runs", json=body)
    assert rerun.status_code == 202
    assert len([r for r in transport.requests if r[2] == "/v1/recognitions"]) == 1


async def test_result_save_failure_never_completes(client, settings, database, app):
    def fault(request):
        if request.url.path.endswith("/results"):
            return httpx.Response(503, json={"detail": "database unavailable"})
        return None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    with pytest.raises(httpx.HTTPStatusError):
        await execute(database, settings, transport, accepted)
    response = (await client.get(BASE + f"/tasks/{accepted['task_id']}/results")).json()
    assert response["status"] == "failed"
    assert not response["available"]


async def test_stage_cannot_restart_or_skip(client, database):
    accepted = await submit(client)
    database.claim()
    path = BASE + f"/internal/runs/{accepted['run_id']}/stages"
    headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
    assert (await client.post(path, headers=headers, json={"stage": "02", "event": "started"})).status_code == 409
    assert (await client.post(path, headers=headers, json={"stage": "01", "event": "started"})).status_code == 200
    assert (await client.post(path, headers=headers, json={"stage": "01", "event": "started"})).status_code == 409


@pytest.mark.parametrize("response_kind", ["success_without_receipt", "timeout", "http_error"])
async def test_worker_requires_saved_result(client, settings, database, response_kind):
    accepted = await submit(client)

    async def handler(request):
        assert json.loads(request.content)["session_id"] == accepted["run_id"]
        if response_kind == "timeout":
            raise httpx.ReadTimeout("response lost")
        return httpx.Response(200 if response_kind == "success_without_receipt" else 500, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await run_once(database, settings, http)
        assert not await run_once(database, settings, http)
    assert (await client.get(BASE + f"/tasks/{accepted['task_id']}")).json()["status"] == "needs_confirmation"


async def test_worker_http_contract_drives_pipeline(client, settings, database, app):
    flow = FastAPI()
    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings), "flow": flow})

    @flow.post("/api/v1/run/consumable-verification")
    async def run(body: dict):
        assert body["input_type"] == "any"  # Custom Verification input and built-in Chat Input both receive the task.
        context = json.loads(body["input_value"])
        async with httpx.AsyncClient(transport=transport) as http:
            for stage in range(9):
                context = await Pipeline(settings, http).execute(f"{stage:02d}", context)
        return {"outputs": [context["receipt"]]}

    accepted = await submit(client)
    async with httpx.AsyncClient(transport=transport) as http:
        assert await run_once(database, settings, http)
    assert (await client.get(BASE + f"/tasks/{accepted['task_id']}/results")).json()["status"] == "completed"


async def test_completion_transaction_rolls_back_on_result_insert_failure(client, settings, database, transport):
    accepted = await submit(client)

    def reject_result(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO") and ".result " in statement:
            raise OperationalError(statement, {}, RuntimeError("simulated disk failure"))

    event.listen(database.engine, "before_cursor_execute", reject_result)
    try:
        with pytest.raises(OperationalError):
            await execute(database, settings, transport, accepted)
    finally:
        event.remove(database.engine, "before_cursor_execute", reject_result)
    with database.sessions() as session:
        assert session.get(Run, accepted["run_id"]).status == "failed"
        assert session.scalar(select(Result)) is None


async def test_identical_result_save_receipt_and_conflicting_rewrite(client, settings, database, transport):
    accepted = await submit(client)
    context = await execute(database, settings, transport, accepted)
    headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
    path = BASE + f"/internal/runs/{accepted['run_id']}/results"
    same = await client.post(path, json=context["result"], headers=headers)
    assert same.status_code == 200
    assert same.json() == context["receipt"]
    changed = dict(context["result"], rule_version="different")
    assert (await client.post(path, json=changed, headers=headers)).status_code == 409


async def test_missing_settlement_time_skips_imaging_and_retains_other_result(client, settings, database, app):
    from langflow.verification.demo import settlement_fixture

    def fault(request):
        if request.url.path == "/v1/settlements/query":
            hip = settlement_fixture("hip")
            hip["settlement_time"] = None
            return httpx.Response(200, json={"simulated": True, "items": [hip, settlement_fixture("knee")]})
        if request.url.path == "/api/v2/study/list":
            assert request.url.params["system_patient_id"] != "synthetic-patient-hip"
        return None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    context = await execute(database, settings, transport, accepted)
    hip, knee = context["result"]["results"]
    assert "settlement_time_missing" in hip["quantity"]["reasons"]
    assert knee["conclusion"] == "consistent"


async def test_model_partial_failure_retains_other_scope(client, settings, database, app):
    def fault(request):
        if request.url.path == "/v1/recognitions":
            body = json.loads(request.content)
            if body["target_category"] == "hip_prosthesis":
                return httpx.Response(
                    200,
                    json={
                        "status": "partial_failed",
                        "raw_count": "0",
                        "count": None,
                        "study_ids": body["study_ids"],
                        "processed_uids": [body["images"][0]["image_uid"]],
                        "failed": {body["images"][1]["image_uid"]: "decode_failed"},
                        "simulated": True,
                    },
                )
        return None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    await execute(database, settings, transport, accepted)
    data = (await client.get(BASE + f"/tasks/{accepted['task_id']}/results")).json()
    assert data["status"] == "partial_failed"
    hip, knee = data["result"]["results"]
    assert hip["quantity"]["status"] == "not_compared"
    assert hip["quantity"]["delta"] is None
    assert knee["conclusion"] == "consistent"


async def test_entry_rejects_scope_tampering(client, settings, database, transport):
    accepted = await submit(client)
    database.claim()
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(ValueError, match="immutable task scope"):
            await Pipeline(settings, http).enter(
                {"task_id": accepted["task_id"], "run_id": accepted["run_id"], "detail_ids": ["different-detail"]}
            )


async def test_no_images_is_not_a_zero_detection(client, settings, database, app):
    def fault(request):
        if request.url.path.endswith("/sop-instance-uid"):
            return httpx.Response(200, json={"code": 200, "data": []})
        return None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    context = await execute(database, settings, transport, accepted)
    assert all(item["quantity"]["status"] == "not_compared" for item in context["result"]["results"])
    assert all(path != "/v1/recognitions" for _method, _host, path in transport.requests)


@pytest.mark.parametrize(
    "response", [httpx.Response(200, json=[1, 2]), httpx.Response(502, text="upstream unavailable")]
)
async def test_malformed_model_response_is_retained(client, settings, database, app, response):
    def fault(request):
        return response if request.url.path == "/v1/recognitions" else None

    transport = ServiceTransport({"business": app, "upstream": create_demo_app(settings)}, fault)
    accepted = await submit(client)
    with pytest.raises(ExecutionUncertain):
        await execute(database, settings, transport, accepted)
    with database.sessions() as session:
        request = session.scalar(select(ModelRequest))
        assert request.status == "needs_confirmation"
        assert request.raw_response
