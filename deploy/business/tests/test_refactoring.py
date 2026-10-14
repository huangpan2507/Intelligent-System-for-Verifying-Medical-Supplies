"""Decision regressions: keep counterexamples executable, including ablations."""

from uuid import uuid4

import pyarrow as pa
import pytest

from langflow.business.datasets import DatasetStore, IncompleteReadError, ROW_ID
from langflow.business.relational import identity_queries
from test_workflows import env, upstream, OWNER  # noqa: F401 - shared integration fixtures


def test_read_failure_seals_prior_batches(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))

    def batches():
        yield [{"key": "saved"}]
        raise ConnectionError("next page failed")

    with pytest.raises(IncompleteReadError) as failure:
        store.write_batches("source", batches(), pa.schema([("key", pa.string())]))
    page = store.page(failure.value.receipt["id"])
    assert page["rows"][0]["key"] == "saved"
    assert page["provenance"]["completeness"]["state"] == "incomplete"


def test_identity_uses_all_original_facts_after_projection(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    raw = store.write_batches(
        "raw",
        [
            [
                {"id": "same", "value": 10, "patient": "A"},
                {"id": "same", "value": 10, "patient": "A"},
                {"id": "conflict", "value": 20, "patient": "A"},
                {"id": "conflict", "value": 20, "patient": "B"},
                {"id": None, "value": 30, "patient": "C"},
                {"id": None, "value": 30, "patient": "C"},
                {"id": "distinct", "value": 10, "patient": "A"},
            ]
        ],
        pa.schema([("id", pa.string()), ("value", pa.int64()), ("patient", pa.string())]),
    )
    projected = store.query("projection", f"SELECT id, value, {ROW_ID} FROM {store.relation(raw['id'])}")
    store.link(
        projected,
        f"SELECT {ROW_ID} row_id, '{raw['id']}' parent_id, {ROW_ID} parent_row_id FROM {store.relation(raw['id'])}",
        [raw["id"]],
    )
    queries = identity_queries(
        {"identity": {"name": "detail", "namespace": "system", "keys": ["id"]}},
        store.relation(projected["id"]),
        ["id", "value", ROW_ID],
        store.facts(projected["id"]),
    )
    results = {
        port: store.page(store.query("validation", query, port=port)["id"])["rows"] for port, query in queries.items()
    }
    assert {r["id"] for r in results["valid"]} == {"same", "distinct"}
    assert set(results) == {"valid", "issues"}
    assert len(results["issues"]) == 5
    errors = [r for r in results["issues"] if r["_issue_severity"] == "error"]
    notices = [r for r in results["issues"] if r["_issue_severity"] == "info"]
    assert len(errors) == 4 and len(notices) == 1
    assert {r["_issue_reason"] for r in errors} == {"identity_conflict", "missing_identity"}
    assert notices[0]["_identity_status"] == "exact_duplicate" and notices[0]["_issue_reason"] == ""
    # Ablation: an ordinary required-field check cannot enforce the original-fact identity invariant.
    from langflow.business.relational import unary_query

    unguarded = unary_query("validate", {}, store.relation(projected["id"]), ["id", "value", ROW_ID])
    assert store.query("without_identity", unguarded["valid"])["row_count"] == 7


def test_union_arbitrary_deduplication_is_rejected_at_publication(env):
    from langflow.business.compiler import inspect_graph
    from test_workflows import file_graph

    db, settings = env
    graph = file_graph(env)
    graph["nodes"].insert(1, {"id": "Union", "kind": "union", "config": {"deduplicate": True, "keys": ["code"]}})
    graph["edges"] = [{"source": "Source", "target": "Union"}, {"source": "Union", "target": "Result"}]
    with pytest.raises(ValueError, match="downstream Validate"):
        inspect_graph(graph, db, settings, OWNER)


def test_decimal_schema_retains_declared_scale():
    from langflow.business.compiler import sql_type
    from langflow.business.sources import arrow_schema

    assert sql_type("decimal128(22, 9)") == "DECIMAL(22,9)"
    assert (
        str(arrow_schema([{"name": "amount", "type": "number", "precision": 22, "scale": 9}]).field("amount").type)
        == "decimal128(22, 9)"
    )


def verification_graph(env):
    from test_workflows import file_graph
    from langflow.business.templates import node, edge

    graph = file_graph(env)
    graph["nodes"] = [
        graph["nodes"][0],
        node("Identity", "validate", {"identity": {"name": "detail", "namespace": "example", "keys": ["code"]}}),
        node("Selected", "filter", {"conditions": [{"field": "code", "op": "eq", "value": "A"}]}),
        node("Compare", "compare", {"comparisons": [{"left": "value", "right": "value"}]}),
        node(
            "Result",
            "output",
            {
                "name": "Result",
                "primary": True,
                "obligation": {
                    "mode": "verification",
                    "sources": [{"node": "Source", "identity": "Identity"}],
                    "checks": [
                        {
                            "name": "value",
                            "units": {"node": "Identity", "port": "valid"},
                            "results": [{"node": "Compare", "port": "data", "status_field": "_comparison_status"}],
                        }
                    ],
                },
            },
        ),
    ]
    graph["edges"] = [
        edge("Source", "Identity"),
        edge("Identity", "Selected", "valid"),
        edge("Selected", "Compare", "matched"),
        edge("Compare", "Result"),
    ]
    return graph


async def test_final_audit_finds_unwired_record_and_ablation_hides_it(env):
    from test_workflows import save_release, execute_release
    from langflow.business.coverage import finalize

    runtime = await execute_release(env, save_release(env, verification_graph(env)))
    assert not runtime.failures
    summary = finalize(runtime)
    assert summary["state"] == "gaps"
    assert summary["received_records"] == summary["business_identities"] == 2
    assert summary["coverage_gap_records"] == 1
    assert summary["checks"][0]["effective"] == 1
    assert summary["checks"][0]["counts"] == {"equal": 1, "uncompared": 1}
    # Ablation: remove only the obligation. Same outputs and input no longer reveal the missing B.
    runtime.package["obligation"] = {"mode": "ordinary"}
    assert finalize(runtime)["state"] == "not_required"


async def test_subflow_and_multiport_lineage_run_without_recursive_scheduler(env):
    from test_workflows import save_release, execute_release
    from langflow.business.templates import edge, node

    graph = verification_graph(env)
    graph["nodes"][-1]["config"].pop("obligation")
    graph["nodes"] += [node("Excluded", "output", {"name": "Excluded"})]
    graph["edges"] += [edge("Selected", "Excluded", "unmatched")]
    runtime = await execute_release(env, save_release(env, graph))
    assert not runtime.failures
    for name in ["Result", "Excluded"]:
        with runtime.store.engine() as db:
            lineage = db.execute(
                f"SELECT * FROM {runtime.store.lineage(runtime.outputs[name]['data']['id'])}"
            ).fetchall()
        assert len(lineage) == 1


def test_model_receipt_precedes_send_timeout_unknown_no_retry(env, monkeypatch):
    import httpx
    from types import SimpleNamespace
    from sqlalchemy import select
    from langflow.business.models import ExternalRequest
    from langflow.business.sources import model_read
    import langflow.business.sources as sources

    database, settings = env
    store = DatasetStore(database, str(uuid4()))
    source = store.write_batches("objects", [[{"unit": "A"}, {"unit": "B"}]], pa.schema([("unit", pa.string())]))
    calls = []

    def receive(request):
        with database.sessions() as session:
            receipts = list(session.scalars(select(ExternalRequest).where(ExternalRequest.task_id == store.task_id)))
        assert len(receipts) == len(calls) + 1
        assert receipts[-1].transport == "attempted"
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("Remote accepted but reply lost", request=request)
        return httpx.Response(200, json={"observed": "ok"})

    monkeypatch.setattr(
        sources,
        "client_for",
        lambda *args: httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(receive)),
    )
    outputs = model_read(
        store,
        "Model",
        {"input_fields": ["unit"], "fields": [{"name": "observed", "type": "text"}]},
        SimpleNamespace(id=str(uuid4())),
        settings,
        source,
    )
    assert len(calls) == 2
    assert outputs["data"]["row_count"] == outputs["issues"]["row_count"] == 1
    with database.sessions() as session:
        receipts = list(session.scalars(select(ExternalRequest).order_by(ExternalRequest.created_at)))
    assert (receipts[0].remote, receipts[0].transport, receipts[0].validity) == (
        "unknown",
        "transport_error",
        "invalid",
    )
    assert receipts[1].remote == "completed"
    # Failure to persist the request must prevent any additional HTTP call.
    from langflow.business import requests as ledger

    def broken(*args, **kwargs):
        raise OSError("cannot persist")

    monkeypatch.setattr(ledger, "prepare", broken)
    with pytest.raises(OSError):
        model_read(
            store,
            "FailedLedger",
            {"input_fields": ["unit"], "fields": [{"name": "observed", "type": "text"}]},
            SimpleNamespace(id=str(uuid4())),
            settings,
            source,
        )
    assert len(calls) == 2


def test_api_independent_scope_continues_but_shared_failure_is_incomplete(env, monkeypatch):
    import httpx
    from types import SimpleNamespace
    from langflow.business.sources import api_read
    import langflow.business.sources as sources

    db, settings = env
    store = DatasetStore(db, str(uuid4()))
    source = store.write_batches("units", [[{"unit": "A"}, {"unit": "B"}]], pa.schema([("unit", pa.string())]))

    def respond(request):
        if request.url.params.get("unit") == "A" or request.url.params.get("page") == "2":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"items": [{"value": 10}]})

    monkeypatch.setattr(
        sources,
        "client_for",
        lambda *args: httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)),
    )
    base = {"path": "/records", "items_path": "items", "fields": [{"name": "value", "type": "integer"}]}
    independent = api_read(
        store,
        "Independent",
        {
            **base,
            "body": {"unit": {"field": "unit"}},
            "completeness": {"scope": "object", "basis": "one complete response per requested unit"},
        },
        SimpleNamespace(id=str(uuid4())),
        settings,
        {},
        source,
    )
    assert independent["data"]["row_count"] == independent["issues"]["row_count"] == 1
    assert independent["data"]["completeness"]["state"] == "complete"
    shared = api_read(
        store,
        "Shared",
        {**base, "pagination": "page", "completeness": {"scope": "range", "basis": "empty page terminates full range"}},
        SimpleNamespace(id=str(uuid4())),
        settings,
        {},
    )
    assert shared["data"]["row_count"] == 1
    assert shared["data"]["completeness"]["state"] == "incomplete"


def test_api_schema_failure_keeps_received_raw_records(env, monkeypatch):
    import json
    import httpx
    from types import SimpleNamespace
    import langflow.business.sources as sources

    db, settings = env
    store = DatasetStore(db, str(uuid4()))
    records = [{"id": "A", "amount": "1.00"}, {"id": "B", "amount": "invalid", "extra": "preserved"}]
    monkeypatch.setattr(
        sources,
        "client_for",
        lambda *args: httpx.Client(
            base_url="http://fixture",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"items": records})),
        ),
    )
    result = sources.api_read(
        store,
        "Source",
        {
            "path": "/records",
            "items_path": "items",
            "pagination": "none",
            "fields": [{"name": "id", "type": "text"}, {"name": "amount", "type": "number", "scale": 2}],
            "completeness": {"scope": "range", "basis": "one complete response"},
        },
        SimpleNamespace(id=str(uuid4())),
        settings,
        {},
    )
    raw = store.page(result["data"]["id"])["rows"]
    assert [json.loads(row["_raw_record"]) for row in raw] == records
    assert result["data"]["completeness"]["state"] == "incomplete"
    issues = store.page(result["issues"]["id"])["rows"]
    assert len(issues) == 1
    assert json.loads(issues[0]["_raw_response"])["items"] == records


def test_execution_digest_excludes_demo_and_keeps_real_dependencies():
    from langflow.business.compiler import EXECUTION_MODULES

    assert {"runtime", "relational", "sources", "coverage", "requests"} <= EXECUTION_MODULES
    assert not {"demo", "templates", "api"} & EXECUTION_MODULES


def test_model_pending_malformed_and_partial_observations_are_distinct(env, monkeypatch):
    import httpx
    from types import SimpleNamespace
    from sqlalchemy import select
    from langflow.business.models import ExternalRequest
    from langflow.business import sources

    db, settings = env
    store = DatasetStore(db, str(uuid4()))
    source = store.write_batches(
        "objects", [[{"key": "pending"}, {"key": "malformed"}, {"key": "partial"}]], pa.schema([("key", pa.string())])
    )
    responses = iter(
        [
            httpx.Response(202, json={"job_id": "remote-1"}),
            httpx.Response(200, text="malformed provider body"),
            httpx.Response(200, json={"category": "known", "quantity": None}),
        ]
    )
    monkeypatch.setattr(
        sources,
        "client_for",
        lambda *args: httpx.Client(
            base_url="http://fixture", transport=httpx.MockTransport(lambda request: next(responses))
        ),
    )
    outputs = sources.model_read(
        store,
        "Model",
        {
            "input_fields": ["key"],
            "fields": [
                {"name": "category", "type": "text", "nullable": False},
                {"name": "quantity", "type": "number", "nullable": True},
            ],
        },
        SimpleNamespace(id=str(uuid4())),
        settings,
        source,
    )
    assert outputs["data"]["row_count"] == 1 and outputs["issues"]["row_count"] == 2
    with db.sessions() as session:
        receipts = list(session.scalars(select(ExternalRequest).order_by(ExternalRequest.created_at)))
    assert receipts[0].remote == "accepted" and receipts[0].response == {"job_id": "remote-1"}
    assert receipts[1].remote == "unknown" and receipts[1].response["raw_body"] == "malformed provider body"
    assert receipts[2].validity == "valid"


async def test_invalid_member_blocks_its_group_not_independent_group(env):
    from langflow.business.templates import edge, node
    from test_workflows import save_release, execute_release, file_graph
    from langflow.business.sources import file_path

    graph = file_graph(env)
    source = graph["nodes"][0]
    file_path(OWNER, source["config"]["file_id"]).write_text("code,value,extra\nA,10,x\nA,-5,x\nB,20,x\n")
    graph["nodes"] = [
        source,
        node("Validate", "validate", {"conditions": [{"field": "value", "op": "ge", "value": 0}]}),
        node(
            "Totals",
            "aggregate",
            {"group_by": ["code"], "metrics": [{"operation": "sum", "field": "value", "output": "total"}]},
        ),
        node("Compare", "compare", {"comparisons": [{"left": "total", "right": "total"}]}),
        node("Result", "output", {"name": "result"}),
    ]
    graph["edges"] = [
        edge("Source", "Validate"),
        edge("Validate", "Totals", "valid"),
        edge("Totals", "Compare"),
        edge("Compare", "Result"),
    ]
    runtime = await execute_release(env, save_release(env, graph))
    assert not runtime.failures
    rows = runtime.store.page(runtime.outputs["Result"]["data"]["id"])["rows"]
    assert {r["code"]: r["_comparison_status"] for r in rows} == {"A": "unknown", "B": "equal"}
    from langflow.business.relational import unary_query

    # Ablation: only erase the invalid-member dependency, keeping exactly the same received facts.
    totals = runtime.outputs["Totals"]["data"]
    unguarded = unary_query(
        "compare",
        {"comparisons": [{"left": "total", "right": "total"}]},
        f"(SELECT * EXCLUDE(_blocking_reason) FROM {runtime.store.relation(totals['id'])})",
        [f["name"] for f in totals["fields"] if f["name"] != "_blocking_reason"],
    )["data"]
    without_scope = runtime.store.page(runtime.store.query("without_scope", unguarded)["id"])["rows"]
    assert {r["code"]: r["_comparison_status"] for r in without_scope} == {"A": "equal", "B": "equal"}


def test_numeric_conversion_never_silently_rounds(env):
    from langflow.business.relational import unary_query

    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    source = store.write_batches(
        "raw", [[{"value": "1.000000001"}, {"value": "bad"}, {"value": "1.2"}]], pa.schema([("value", pa.string())])
    )
    query = unary_query(
        "transform",
        {"transforms": [{"field": "value", "output": "amount", "operation": "cast", "type": "number", "scale": 6}]},
        store.relation(source["id"]),
        ["value", ROW_ID],
    )["data"]
    rows = store.page(store.query("cast", query)["id"])["rows"]
    assert [r["_issue_reason"] for r in rows] == ["conversion:amount", "conversion:amount", ""]
    assert [r["amount"] for r in rows[:2]] == [None, None]


async def test_maintenance_keeps_idempotency_and_request_source_isolation(env):
    import httpx
    from langflow.business.models import ExternalRequest, Scheme, Task
    from langflow.business.maintenance import change
    from langflow.verification.api import create_app
    from test_workflows import file_graph, save_release

    db, settings = env
    release = save_release(env, file_graph(env))
    with db.sessions.begin() as session:
        scheme = session.get(Scheme, release.scheme_code)
        scheme.active_release_id, scheme.allowed_sources = release.id, ["a"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://fixture"
    ) as http:
        auth = {"Authorization": "Bearer " + "a" * 20}
        body = {"scheme": "test", "parameters": {}}
        submitted = await http.post("/api/v1/business/tasks", headers={**auth, "Idempotency-Key": "one"}, json=body)
        assert submitted.status_code == 202
        task_id = submitted.json()["id"]
        state = change(db, "close")
        assert task_id in state["pending_tasks"] and not state["safe_to_upgrade"]
        assert (
            await http.post("/api/v1/business/tasks", headers={**auth, "Idempotency-Key": "one"}, json=body)
        ).json()["id"] == task_id
        assert (
            await http.post("/api/v1/business/tasks", headers={**auth, "Idempotency-Key": "two"}, json=body)
        ).status_code == 503
        with pytest.raises(ValueError, match="not drained"):
            change(db, "open")
        with db.sessions.begin() as session:
            session.get(Task, task_id).status = "completed"
            receipt = ExternalRequest(
                task_id=task_id,
                node_id="Model",
                input_dataset_id=str(uuid4()),
                input_row_id=0,
                connection_id=str(uuid4()),
                payload={"example": True},
            )
            session.add(receipt)
            session.flush()
        for suffix in ["requests", "requests/" + receipt.id]:
            url = f"/api/v1/business/tasks/{task_id}/{suffix}"
            assert (await http.get(url, headers=auth)).status_code == 200
            assert (await http.get(url, headers={"Authorization": "Bearer " + "b" * 20})).status_code == 404
        assert change(db, "open")["status"] == "open"


async def test_republish_uses_selected_immutable_release_not_newer_draft(env):
    import httpx
    from copy import deepcopy
    from langflow.business.models import Release, Scheme
    from langflow.verification.api import create_app
    from test_workflows import file_graph, save_release

    db, settings = env
    release = save_release(env, file_graph(env))
    changed = deepcopy(release.package["graph"])
    changed["nodes"][-1]["config"]["name"] = "Unpublished draft"
    with db.sessions.begin() as session:
        scheme = session.get(Scheme, "test")
        scheme.draft = changed
        scheme.revision += 1
        revision = scheme.revision
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://fixture"
    ) as http:
        response = await http.post(
            f"/api/v1/business/internal/schemes/test/releases/from/{release.id}",
            headers={
                "Authorization": "Bearer " + settings.internal_token.get_secret_value(),
                "X-Business-Actor": OWNER,
            },
            json={"expected_revision": revision},
        )
    assert response.status_code == 201, response.text
    assert response.json()["package"]["graph"] == release.package["graph"]
    assert response.json()["id"] != release.id
    with db.sessions() as session:
        assert session.get(Scheme, "test").draft == changed
        assert session.get(Release, release.id).package == release.package


async def test_consumable_three_checks_and_adversarial_dispositions(env, upstream):
    from langflow.business.templates import consumables
    from langflow.business.coverage import finalize
    from test_workflows import save_release, execute_release

    runtime = await execute_release(env, save_release(env, consumables(upstream.id)), {"scenario": "adversarial"})
    assert not runtime.failures
    summary = finalize(runtime)
    assert summary["received_records"] == 18
    assert summary["business_identities"] == 15
    assert summary["missing_identity_records"] == 1
    checks = {c["name"]: c for c in summary["checks"]}
    assert set(checks) == {"category", "quantity", "fee"}
    assert checks["category"]["effective"] > checks["quantity"]["effective"] > checks["fee"]["effective"]
    # Invalid professional quantity is not a comparison; same template still produces valid positive controls.
    quantities = runtime.store.page(runtime.outputs["Results"]["data"]["id"])["rows"]
    assert {r["_comparison_status"] for r in quantities} >= {"equal", "different"}
    assert all(r["left_patient_id"] != "case-negative" for r in quantities)
    from langflow.business.models import ExternalRequest
    from sqlalchemy import select

    with runtime.database.sessions() as session:
        requests = list(session.scalars(select(ExternalRequest).where(ExternalRequest.task_id == runtime.task.id)))
    assert requests and all("quantity" not in r.payload and r.payload.get("evidence") for r in requests)
    # Ablation: bypass the template's quantity preconditions, not the model or its fixture responses.
    from langflow.business.relational import fields_of, unary_query

    observations = runtime.outputs["ObservationChecks"]["valid"]
    without_gate = unary_query(
        "compare",
        {"comparisons": [{"left": "settled_quantity", "right": "recognized_quantity", "mode": "numeric"}]},
        runtime.store.relation(observations["id"]),
        fields_of(observations),
    )["data"]
    rows = runtime.store.page(runtime.store.query("without_gate", without_gate)["id"])["rows"]
    assert next(r for r in rows if r["left_patient_id"] == "case-negative")["_comparison_status"] == "different"
