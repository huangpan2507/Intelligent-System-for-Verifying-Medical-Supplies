from decimal import Decimal
from uuid import uuid4

import httpx
import pyarrow as pa
import pytest
from langflow.business.compiler import inspect_graph
from langflow.business.datasets import ROW_ID, DatasetStore
from langflow.business.models import Dataset, Release, Scheme, Task, initialize
from langflow.business.relational import join_queries, unary_query
from langflow.verification.database import Database, fingerprint
from langflow.verification.settings import VerificationSettings

OWNER = "c23d7b4c-e0c9-4eee-a09c-35a8dfd7c7f4"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BUSINESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LANGFLOW_CONFIG_DIR", str(tmp_path / "platform"))
    db = Database(f"sqlite:///{tmp_path}/test.db")
    db.initialize()
    initialize(db)
    settings = VerificationSettings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        clients={"a": "a" * 20, "b": "b" * 20},
        internal_token="i" * 20,
        langflow_api_key="l" * 20,
        demo_mode=True,
    )
    yield db, settings
    db.engine.dispose()


def write(store, name, rows, schema):
    return store.write_batches(name, [rows], schema)


def test_cross_batch_aggregation_and_full_join(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    orders = write(
        store,
        "orders",
        [
            {"order_no": "O001", "amount": 100, "unused": "keep"},
            {"order_no": "O002", "amount": 200, "unused": "keep"},
            {"order_no": "O003", "amount": 300, "unused": "keep"},
        ],
        pa.schema([("order_no", pa.string()), ("amount", pa.int64()), ("unused", pa.string())]),
    )
    schema = pa.schema([("biz_no", pa.string()), ("amount", pa.int64())])
    payments = store.write_batches(
        "payments",
        [
            [{"biz_no": "O001", "amount": 60}],
            [{"biz_no": "O001", "amount": 40}, {"biz_no": "O002", "amount": 180}, {"biz_no": "O004", "amount": 50}],
        ],
        schema,
    )
    aggregate = unary_query(
        "aggregate",
        {"group_by": ["biz_no"], "metrics": [{"field": "amount", "operation": "sum", "output": "total"}]},
        store.relation(payments["id"]),
        ["biz_no", "amount", ROW_ID],
    )["data"]
    grouped = store.query("aggregate", aggregate)
    queries = join_queries(
        {"keys": [{"left": "order_no", "right": "biz_no"}]},
        store.relation(orders["id"]),
        store.relation(grouped["id"]),
        [f["name"] for f in orders["fields"]],
        [f["name"] for f in grouped["fields"]],
    )
    joined = store.query("join", queries["data"])
    compare = unary_query(
        "compare",
        {"comparisons": [{"left": "left_amount", "right": "right_total", "mode": "numeric"}]},
        store.relation(joined["id"]),
        [f["name"] for f in joined["fields"]],
    )["data"]
    result = store.query("compare", compare)
    rows = store.page(result["id"])["rows"]
    assert {r["_comparison_status"] for r in rows} == {"equal", "different", "left_only", "right_only"}
    assert Decimal(str(next(r for r in rows if r["_comparison_status"] == "different")["difference_0"])) == -20
    assert store.page(orders["id"])["rows"][0]["unused"] == "keep"


def test_ambiguous_join_preserves_both_sides_as_issues(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    schema = pa.schema([("key", pa.string())])
    left = write(store, "left", [{"key": "A"}, {"key": "A"}, {"key": None}], schema)
    right = write(store, "right", [{"key": "A"}, {"key": "B"}], schema)
    queries = join_queries(
        {"keys": [{"left": "key", "right": "key"}]},
        store.relation(left["id"]),
        store.relation(right["id"]),
        ["key", ROW_ID],
        ["key", ROW_ID],
    )
    assert store.query("join", queries["data"])["row_count"] == 1
    assert store.query("join", queries["issues"], port="issues")["row_count"] == 4


def test_filter_distinguishes_false_and_unknown(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    source = write(
        store, "source", [{"paid": True}, {"paid": False}, {"paid": None}], pa.schema([("paid", pa.bool_())])
    )
    queries = unary_query(
        "filter",
        {"conditions": [{"field": "paid", "op": "eq", "value": True}]},
        store.relation(source["id"]),
        ["paid", ROW_ID],
    )
    assert {port: store.query("filter", q, port=port)["row_count"] for port, q in queries.items()} == {
        "matched": 1,
        "unmatched": 1,
        "unknown": 1,
    }


def file_graph(env):
    from langflow.business.sources import file_path

    file_id = str(uuid4())
    path = file_path(OWNER, file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("code,value,extra\nA,1,preserved\nB,2,preserved\n")
    return {
        "nodes": [
            {
                "id": "Source",
                "kind": "file",
                "config": {
                    "file_id": file_id,
                    "format": "csv",
                    "fields": [
                        {"name": "code", "type": "text"},
                        {"name": "value", "type": "integer"},
                        {"name": "extra", "type": "text"},
                    ],
                },
            },
            {"id": "Result", "kind": "output", "config": {"name": "Results", "columns": ["code", "value"]}},
        ],
        "edges": [{"source": "Source", "target": "Result", "port": "data", "input": "data"}],
    }


@pytest.mark.parametrize("namespaced", [False, True], ids=["legacy-ids", "native-canvas-ids"])
async def test_actual_langflow_graph_runtime(env, namespaced):
    from langflow.business.components import from_langflow, to_langflow
    from langflow.business.runtime import run_task

    db, settings = env
    graph = file_graph(env)
    if namespaced:
        ids = {node["id"]: f"ext:business:Business{node['kind'].title()}@extra-abc12" for node in graph["nodes"]}
        for node in graph["nodes"]:
            node["id"] = ids[node["id"]]
        for edge in graph["edges"]:
            edge["source"] = ids[edge["source"]]
            edge["target"] = ids[edge["target"]]
    canvas = to_langflow(graph)
    assert len(canvas["nodes"]) == 2
    spec = from_langflow(canvas)
    package = inspect_graph(spec, db, settings, OWNER)
    package["flow_id"] = str(uuid4())
    with db.sessions.begin() as session:
        release = Release(scheme_code="files", version=1, package=package, content_hash=fingerprint(package))
        session.add(release)
        session.flush()
        task = Task(
            owner_id=OWNER,
            source="a",
            idempotency_key="run",
            content_hash="x",
            scheme_code="files",
            release_id=release.id,
            parameters={},
        )
        session.add(task)
        session.flush()
    await run_task(db, settings, task.id)
    with db.sessions() as session:
        task = session.get(Task, task.id)
        assert task.status == "completed"
        assert len(task.results) == 1
        raw = session.scalar(
            __import__("sqlalchemy").select(Dataset).where(Dataset.task_id == task.id, Dataset.raw.is_(True))
        )
    assert DatasetStore(db, task.id).page(raw.id)["rows"][0]["extra"] == "preserved"
    assert "extra" not in DatasetStore(db, task.id).page(task.results[0])["rows"][0]


async def test_source_isolation_idempotency_and_release_pinning(env):
    from langflow.verification.api import create_app

    db, settings = env
    graph = file_graph(env)
    package = inspect_graph(graph, db, settings, OWNER)
    with db.sessions.begin() as session:
        release = Release(scheme_code="test", version=1, package=package, content_hash=fingerprint(package))
        session.add(release)
        session.flush()
        session.add(
            Scheme(
                code="test",
                name="Test",
                owner_id=OWNER,
                flow_id=str(uuid4()),
                draft=graph,
                active_release_id=release.id,
                allowed_sources=["a"],
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        headers = {"Authorization": "Bearer " + "a" * 20, "Idempotency-Key": "one"}
        response = await http.post("/api/v1/business/tasks", headers=headers, json={"scheme": "test", "parameters": {}})
        assert response.status_code == 202, response.text
        task = response.json()
        assert (
            await http.post("/api/v1/business/tasks", headers=headers, json={"scheme": "test", "parameters": {}})
        ).json()["id"] == task["id"]
        assert (
            await http.get(f"/api/v1/business/tasks/{task['id']}", headers={"Authorization": "Bearer " + "b" * 20})
        ).status_code == 404
        assert (
            await http.get("/api/v1/business/schemes", headers={"Authorization": "Bearer " + "b" * 20})
        ).json() == []
        assert (
            await http.post(
                "/api/v1/business/tasks",
                headers=headers,
                json={"scheme": "test", "parameters": {"arbitrary_sql": "select 1"}},
            )
        ).status_code == 409
        assert task["release_id"] == release.id


def save_release(env, graph, code="test"):
    db, settings = env
    package = inspect_graph(graph, db, settings, OWNER)
    with db.sessions.begin() as session:
        release = Release(scheme_code=code, version=1, package=package, content_hash=fingerprint(package))
        session.add(release)
        session.flush()
        session.add(Scheme(code=code, name=code, owner_id=OWNER, flow_id=str(uuid4()), draft=graph))
    return release


async def execute_release(env, release, parameters=None):
    from langflow.business.runtime import Runtime

    db, settings = env
    with db.sessions.begin() as session:
        task = Task(
            owner_id=OWNER,
            source="a",
            idempotency_key=str(uuid4()),
            content_hash="x",
            scheme_code=release.scheme_code,
            release_id=release.id,
            parameters=parameters or {},
        )
        session.add(task)
        session.flush()
    runtime = Runtime(db, settings, task, release.package)
    await runtime.run_graph()
    return runtime


@pytest.fixture
def upstream(env):
    import socket
    import threading
    import time

    import uvicorn
    from fastapi import FastAPI
    from langflow.business.connections import encrypt
    from langflow.business.demo import register_demo
    from langflow.business.models import Connection

    app = FastAPI()
    register_demo(app, lambda: None)

    @app.post("/analyze")
    def analyze(body: dict):
        return {"category": "class-" + body["record"]["code"], "confidence": "0.7"}

    @app.post("/lookup")
    def lookup(body: dict):
        return {"items": [{"answer": body["code"], "unselected": "saved"}]}

    @app.get("/comparison-payments")
    def comparison_payments(page: int = 1):
        pages = {
            1: [{"payment_id": "P01", "biz_no": "O001", "amount": "60.00"}],
            2: [{"payment_id": "P02", "biz_no": "O001", "amount": "40.00"},
                {"payment_id": "P03", "biz_no": "O002", "amount": "180.00"}],
        }
        return {"items": pages.get(page, []), "complete": True}

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    db, settings = env
    with db.sessions.begin() as session:
        connection = Connection(
            owner_id=OWNER,
            name="Synthetic HTTP",
            kind="api",
            config={"base_url": f"http://127.0.0.1:{sock.getsockname()[1]}"},
            secret=encrypt("", settings),
        )
        session.add(connection)
        session.flush()
    yield connection
    server.should_exit = True
    thread.join(timeout=5)
    sock.close()


async def test_consumable_template_preserves_unknowns_and_simulation(env, upstream):
    from langflow.business.templates import consumables

    runtime = await execute_release(
        env,
        save_release(env, consumables(upstream.id)),
        {"hospital": "synthetic-hospital", "start": "2024-01-01", "end": "2027-01-01"},
    )
    result = runtime.store.page(runtime.outputs["Results"]["data"]["id"])
    assert {r["_comparison_status"] for r in result["rows"]} == {"equal", "different"}
    assert all(r["simulated"] for r in result["rows"])
    assert runtime.outputs["UnknownCategories"]["data"]["row_count"] == 1
    assert runtime.outputs["UnknownFacts"]["data"]["row_count"] == 1
    assert runtime.outputs["Targets"]["unmatched"]["row_count"] == 2
    assert runtime.outputs["Settlements"]["data"]["row_count"] == 6
    raw = runtime.store.page(runtime.outputs["Settlements"]["data"]["id"])["rows"]
    assert "item_name" in __import__("json").loads(raw[0]["_raw_record"])


async def test_subflow_uses_frozen_input_and_transformation(env):
    from langflow.business.templates import edge, node

    child = {
        "nodes": [
            node("Input", "parameters", {"dataset_fields": [{"name": "value", "type": "integer"}]}),
            node(
                "Double",
                "transform",
                {"transforms": [{"operation": "expression", "expression": "value * 2", "output": "doubled"}]},
            ),
            node("Result", "output", {"name": "Doubled", "columns": ["value", "doubled"]}),
        ],
        "edges": [edge("Input", "Double"), edge("Double", "Result")],
    }
    release = save_release(env, child, "child")
    parent = file_graph(env)
    parent["nodes"].insert(1, node("Child", "subflow", {"release_id": release.id, "output_node": "Result"}))
    parent["nodes"][-1]["config"]["columns"] = ["doubled"]
    parent["edges"] = [edge("Source", "Child"), edge("Child", "Result")]
    runtime = await execute_release(env, save_release(env, parent, "parent"))
    assert sorted(r["doubled"] for r in runtime.store.page(runtime.output_ids[0])["rows"]) == [2, 4]


async def test_api_record_binding_and_model_after_validation(env, upstream):
    from langflow.business.templates import edge, node

    graph = file_graph(env)
    graph["nodes"] += [
        node("Validate", "validate", {"required": ["code"]}),
        node(
            "Analyze",
            "model",
            {
                "connection": upstream.id,
                "path": "/analyze",
                "input_fields": ["code"],
                "fields": [{"name": "category", "type": "text"}, {"name": "confidence", "type": "number"}],
            },
        ),
        node(
            "Lookup",
            "api",
            {
                "connection": upstream.id,
                "path": "/lookup",
                "method": "POST",
                "body": {"code": {"field": "code"}},
                "items_path": "items",
                "fields": [{"name": "answer", "type": "text"}],
            },
        ),
        node("ModelResult", "output", {"name": "Model"}),
        node("ApiResult", "output", {"name": "API"}),
    ]
    graph["edges"] += [
        edge("Source", "Validate"),
        edge("Validate", "Analyze", "valid"),
        edge("Source", "Lookup"),
        edge("Analyze", "ModelResult"),
        edge("Lookup", "ApiResult"),
    ]
    from langflow.business.field_schema import document_evidence

    lookup = next(n["config"] for n in graph["nodes"] if n["id"] == "Lookup")
    lookup["field_evidence"] = document_evidence(lookup, lookup["fields"], "Test fixture /lookup response contract")
    runtime = await execute_release(env, save_release(env, graph))
    model = runtime.store.page(runtime.outputs["ModelResult"]["data"]["id"])["rows"]
    assert {r["category"] for r in model} == {"class-A", "class-B"}
    api = runtime.store.page(runtime.outputs["ApiResult"]["data"]["id"])["rows"]
    assert {r["answer"] for r in api} == {"A", "B"}
    assert {r["_request_row_id"] for r in api} == {0, 1}


def test_large_integer_aggregation_stays_exact(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    source = write(store, "source", [{"value": 9007199254740993}, {"value": 2}], pa.schema([("value", pa.int64())]))
    query = unary_query(
        "aggregate",
        {"metrics": [{"field": "value", "operation": "sum", "output": "total"}]},
        store.relation(source["id"]),
        ["value", ROW_ID],
    )["data"]
    result = store.query("total", query)
    assert Decimal(store.page(result["id"])["rows"][0]["total"]) == 9007199254740995


def test_repeat_validation_and_comparison_replace_current_status(env):
    db, _ = env
    store = DatasetStore(db, str(uuid4()))
    source = write(store, "source", [{"a": 1, "b": 2}], pa.schema([("a", pa.int64()), ("b", pa.int64())]))
    validated = store.query(
        "first", unary_query("validate", {"required": ["a"]}, store.relation(source["id"]), ["a", "b", ROW_ID])["valid"]
    )
    fields = [f["name"] for f in validated["fields"]]
    repeat = unary_query(
        "validate", {"conditions": [{"field": "a", "op": "gt", "value": 10}]}, store.relation(validated["id"]), fields
    )
    assert store.query("second", repeat["issues"])["row_count"] == 1
    first = store.query(
        "compare1",
        unary_query(
            "compare", {"comparisons": [{"left": "a", "right": "b"}]}, store.relation(source["id"]), ["a", "b", ROW_ID]
        )["data"],
    )
    second = store.query(
        "compare2",
        unary_query(
            "compare",
            {"comparisons": [{"left": "a", "right": "a"}]},
            store.relation(first["id"]),
            [f["name"] for f in first["fields"]],
        )["data"],
    )
    assert store.page(first["id"])["rows"][0]["_comparison_status"] == "different"
    assert store.page(second["id"])["rows"][0]["_comparison_status"] == "equal"


async def test_legacy_migration_closes_intake_preserves_history(env):
    from langflow.business.migration import stop_legacy_intake
    from langflow.verification.api import create_app

    db, settings = env
    assert stop_legacy_intake(db)["status"] == "complete"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        headers = {"Authorization": "Bearer " + "a" * 20, "Idempotency-Key": "legacy"}
        response = await http.post(
            "/api/v1/verification/tasks",
            headers=headers,
            json={
                "hospital_scope": "test",
                "rule": "test",
                "settlement_time_range": {
                    "start_inclusive": "2024-01-01T00:00:00Z",
                    "end_exclusive": "2024-02-01T00:00:00Z",
                },
            },
        )
        assert response.status_code == 410
        internal = {"Authorization": "Bearer " + "i" * 20, "X-Verification-Actor": OWNER}
        assert (await http.get("/api/v1/verification/internal/rules", headers=internal)).status_code == 200
        assert (
            await http.post(
                "/api/v1/verification/internal/rules",
                headers=internal,
                json={"code": "new", "name": "new", "flow_id": str(uuid4())},
            )
        ).status_code == 410


def test_native_canvas_handles_match_templates_and_reject_edited_code():
    from langflow.business.components import from_langflow, to_langflow
    from langflow.business.templates import consumables

    canvas = to_langflow(consumables("connection"))
    for edge in canvas["edges"]:
        target = next(n for n in canvas["nodes"] if n["id"] == edge["target"])
        handle = edge["data"]["targetHandle"]
        field = target["data"]["node"]["template"][handle["fieldName"]]
        assert handle["type"] == field["type"]
        assert handle["inputTypes"] == field["input_types"]
    assert len(from_langflow(canvas)["edges"]) == len(consumables()["edges"])
    code = canvas["nodes"][0]["data"]["node"]["template"]["code"]
    code["value"] += '\nraise RuntimeError("unregistered source")\n'
    with pytest.raises(ValueError, match="registered"):
        from_langflow(canvas)


async def test_union_branches_and_primary_result(env):
    from langflow.business.templates import edge, node

    graph = file_graph(env)
    graph["nodes"] += [
        node(
            "Second",
            "transform",
            {"transforms": [{"operation": "expression", "expression": "value + 10", "output": "value"}]},
        ),
        node("Append", "union", {}),
        node("Appended", "output", {"name": "Appended", "primary": True}),
    ]
    graph["edges"] += [
        edge("Source", "Second"),
        edge("Source", "Append"),
        edge("Second", "Append"),
        edge("Append", "Appended"),
    ]
    runtime = await execute_release(env, save_release(env, graph))
    assert runtime.output_ids[0] == runtime.outputs["Appended"]["data"]["id"]
    rows = runtime.store.page(runtime.output_ids[0])["rows"]
    assert sorted(r["value"] for r in rows) == [1, 2, 11, 12]
    assert len({r[ROW_ID] for r in rows}) == 4
    assert len({r["_source_dataset_id"] for r in rows}) == 2


async def test_migration_waits_for_started_runs_preserves_rejected_runs(env):
    from langflow.business.migration import stop_legacy_intake
    from langflow.verification.api import create_app
    from langflow.verification.database import (
        Run,
        RuleDefinition,
        ReleaseCandidate,
        RuleRelease,
        ExecutionBinding,
        Task as LegacyTask,
    )

    db, settings = env
    with db.sessions.begin() as session:
        definition = RuleDefinition(code="history", name="History", flow_id=str(uuid4()), owner_id=OWNER)
        session.add(definition)
        session.flush()
        candidate = ReleaseCandidate(
            rule_code=definition.code, content_hash="fixture", package={}, author_id=OWNER, validation={}, note=""
        )
        session.add(candidate)
        session.flush()
        release = RuleRelease(
            rule_code=definition.code,
            version=1,
            candidate_id=candidate.id,
            content_hash="fixture",
            package={},
            author_id=OWNER,
            note="",
        )
        session.add(release)
        session.flush()
        binding = ExecutionBinding(release_id=release.id, config={})
        session.add(binding)
        session.flush()
        runs = []
        for execution_started in [False, True]:
            run_id = str(uuid4())
            task = LegacyTask(
                source_system="a", external_task_id=run_id, content_hash="fixture", payload={}, current_run_id=run_id
            )
            session.add(task)
            session.flush()
            run = Run(
                id=run_id,
                task_id=task.id,
                release_id=release.id,
                binding_id=binding.id,
                policy={"rule_version": 1},
                status="needs_confirmation",
                execution_started=execution_started,
            )
            session.add(run)
            runs.append(run)
        session.flush()
        never_started, started = runs
    status = stop_legacy_intake(db)
    assert status["status"] == "draining"
    assert status["pending_runs"] == [started.id]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        headers = {"Authorization": "Bearer " + "a" * 20}
        body = {"confirmed_execution_ended": True, "reason": "Operator checked that execution ended"}
        response = await http.post(
            f"/api/v1/verification/tasks/{started.task_id}/runs/{started.id}/confirmation",
            headers=headers,
            json=body,
        )
        assert response.status_code == 200
        status = stop_legacy_intake(db)
        assert status["status"] == "complete"
        assert status["unstarted_historical_runs"] == [never_started.id]
        response = await http.post(
            f"/api/v1/verification/tasks/{never_started.task_id}/runs/{never_started.id}/confirmation",
            headers=headers,
            json=body,
        )
        assert response.status_code == 410
    with db.sessions() as session:
        assert session.get(Run, never_started.id).status == "needs_confirmation"
