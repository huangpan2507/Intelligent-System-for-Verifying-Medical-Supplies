"""Field discovery must work without executing a workflow or trusting invented names."""

from copy import deepcopy
from http import HTTPStatus

import pytest
from langflow.business.compiler import inspect_graph
from langflow.business.field_schema import (
    api_preview,
    document_evidence,
    fields_from_schema,
    validate_evidence,
    validate_record,
)
from test_workflows import OWNER, env, execute_release, save_release, upstream  # noqa: F401


def api_config(connection):
    return {
        "connection": connection.id,
        "path": "/lookup",
        "method": "POST",
        "body": {"code": "A"},
        "items_path": "items",
        "fields": [{"name": "answer", "type": "text"}],
    }


def test_document_contract_works_without_request_and_is_bound_to_source(env, upstream):
    _, settings = env
    config = api_config(upstream)
    config["field_evidence"] = document_evidence(config, config["fields"], "Provider contract v1")
    validate_evidence(config, upstream, settings, OWNER)
    config["body"]["code"] = "B"
    with pytest.raises(ValueError, match="changed"):
        validate_evidence(config, upstream, settings, OWNER)
    config["body"]["code"] = "A"
    config["path"] = "/another-interface"
    with pytest.raises(ValueError, match="changed"):
        validate_evidence(config, upstream, settings, OWNER)


def test_sample_is_real_and_cannot_be_used_for_invented_fields(env, upstream):
    _, settings = env
    config = api_config(upstream)
    result = api_preview(upstream, settings, config, {}, {}, OWNER)
    assert result["rows"][0]["answer"] == "A"
    assert {f["name"] for f in result["fields"]} == {"answer", "unselected"}
    config["field_evidence"] = result["field_evidence"]
    validate_evidence(config, upstream, settings, OWNER)
    config["fields"] = [{"name": "invented", "type": "text"}]
    with pytest.raises(ValueError, match=r"observed|evidence"):
        validate_evidence(config, upstream, settings, OWNER)
    config["field_evidence"]["fields"].append({"name": "invented", "type": "text"})
    with pytest.raises(ValueError, match="proof"):
        validate_evidence(config, upstream, settings, OWNER)
    config["field_evidence"]["proof"] = None
    with pytest.raises(ValueError, match="proof"):
        validate_evidence(config, upstream, settings, OWNER)


def test_record_presence_is_independent_of_nullable():
    fields = [{"name": "code", "type": "text", "nullable": True, "required": True}]
    validate_record({"code": None}, fields)
    with pytest.raises(ValueError, match="code"):
        validate_record({}, fields)
    fields[0].update(required=False, nullable=False)
    validate_record({}, fields)
    with pytest.raises(ValueError, match="code"):
        validate_record({"code": None}, fields)


def test_empty_sample_preserves_document_contract(env, upstream):
    _, settings = env
    config = {
        "connection": upstream.id,
        "path": "/comparison-payments",
        "body": {"page": 99},
        "items_path": "items",
        "fields": [{"name": "payment_id", "type": "text"}],
    }
    config["field_evidence"] = document_evidence(config, config["fields"], "Test fixture payment contract")
    original = deepcopy(config)
    result = api_preview(upstream, settings, config, {}, {}, OWNER)
    assert result["fields"] == []
    assert result["rows"] == []
    assert config == original
    validate_evidence(config, upstream, settings, OWNER)


def test_preview_reports_document_conflict_without_replacing_it(env, upstream):
    _, settings = env
    config = api_config(upstream)
    config["fields"].append({"name": "absent", "type": "text", "nullable": True})
    config["field_evidence"] = document_evidence(config, config["fields"], "Provider contract requiring absent")
    original = deepcopy(config)
    result = api_preview(upstream, settings, config, {}, {}, OWNER)
    assert "absent" in result["contract_errors"][0]
    assert config == original


def test_discovery_endpoints_are_owner_scoped_and_do_not_create_tasks(env, upstream):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from langflow.business.api import register
    from langflow.business.models import Task
    from sqlalchemy import select

    database, settings = env
    app = FastAPI()
    register(app, database, settings, lambda: None, lambda: "a")
    base = f"/api/v1/business/internal/connections/{upstream.id}"
    config = api_config(upstream)
    with TestClient(app) as client:
        assert (
            client.post(
                base + "/preview", headers={"X-Business-Actor": "different-owner"}, json={"config": config}
            ).status_code
            == HTTPStatus.NOT_FOUND
        )
        headers = {"X-Business-Actor": OWNER}
        contract = client.post(
            base + "/contract",
            headers=headers,
            json={"config": config, "fields": config["fields"], "reference": "Fixture /lookup v1"},
        )
        assert contract.status_code == HTTPStatus.OK
        config.update(contract.json())
        response = client.post(base + "/preview", headers=headers, json={"config": config})
        assert response.status_code == HTTPStatus.OK
        assert response.json()["rows"][0]["answer"] == "A"
        assert (
            client.post(
                base + "/contract",
                headers=headers,
                json={"config": config, "fields": config["fields"], "reference": ""},
            ).status_code
            == HTTPStatus.UNPROCESSABLE_ENTITY
        )
    with database.sessions() as session:
        assert list(session.scalars(select(Task))) == []


@pytest.mark.parametrize("required", [True, False])
async def test_runtime_missing_property_is_not_silently_treated_as_nullable(env, upstream, required):
    config = api_config(upstream)
    config["fields"] = [
        {"name": "answer", "type": "text"},
        {"name": "absent", "type": "text", "required": required, "nullable": True},
    ]
    config["completeness"] = {"scope": "range", "basis": "Fixture /lookup returns the entire response"}
    config["field_evidence"] = document_evidence(config, config["fields"], "Fixture presence contract")
    graph = {
        "nodes": [
            {"id": "Source", "kind": "api", "config": config},
            {
                "id": "Compare",
                "kind": "compare",
                "config": {"comparisons": [{"left": "answer", "right": "answer", "mode": "exact"}]},
            },
            {"id": "Result", "kind": "output", "config": {"name": "Result"}},
        ],
        "edges": [
            {"source": "Source", "target": "Compare", "port": "data", "input": "data"},
            {"source": "Compare", "target": "Result", "port": "data", "input": "data"},
        ],
    }
    runtime = await execute_release(env, save_release(env, graph))
    source = runtime.outputs["Source"]["data"]
    assert source["completeness"]["state"] == ("incomplete" if required else "complete")
    assert runtime.outputs["Source"]["issues"]["row_count"] == int(required)
    result = runtime.store.page(runtime.outputs["Result"]["data"]["id"])["rows"]
    assert result[0]["_comparison_status"] == ("unknown" if required else "equal")
    rows = runtime.store.page(source["id"])["rows"]
    assert rows[0]["absent"] is None
    assert '"answer": "A"' in rows[0]["_raw_record"]
    assert '"absent"' not in rows[0]["_raw_record"]


def test_import_response_schema_resolves_local_refs_and_presence():
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/lookup": {
                "post": {
                    "responses": {
                        "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Response"}}}}
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Response": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["code"],
                                "properties": {
                                    "code": {"type": "string", "nullable": True},
                                    "count": {"type": "integer"},
                                },
                            },
                        }
                    },
                }
            }
        },
    }
    fields = fields_from_schema(document, {"path": "/lookup", "method": "POST", "items_path": "items"})
    assert fields == [
        {"name": "code", "type": "text", "required": True, "nullable": True},
        {"name": "count", "type": "integer", "required": False, "nullable": False},
    ]


@pytest.mark.parametrize("change", ["missing_evidence", "request_field", "context_field", "output_field"])
def test_compile_rejects_unverified_source_and_missing_references(env, upstream, change):
    database, settings = env
    config = api_config(upstream)
    config["field_evidence"] = document_evidence(config, config["fields"], "Fixture /lookup contract")
    graph = {
        "nodes": [
            {"id": "Source", "kind": "api", "config": config},
            {"id": "Result", "kind": "output", "config": {"name": "Result", "columns": ["answer"]}},
        ],
        "edges": [{"source": "Source", "target": "Result", "port": "data", "input": "data"}],
    }
    assert not inspect_graph(graph, database, settings, OWNER)["errors"]
    broken = deepcopy(graph)
    if change == "missing_evidence":
        broken["nodes"][0]["config"].pop("field_evidence")
    elif change == "request_field":
        broken["nodes"][0]["config"]["body"] = {"nested": [{"field": "invented"}]}
        broken["nodes"][0]["config"]["field_evidence"] = document_evidence(
            broken["nodes"][0]["config"], config["fields"], "Fixture changed request contract"
        )
    elif change == "context_field":
        broken["nodes"][0]["config"]["context_fields"] = ["invented"]
    else:
        broken["nodes"][1]["config"]["key_fields"] = ["invented"]
    inspected = inspect_graph(broken, database, settings, OWNER, strict=False)
    assert inspected["errors"]
    with pytest.raises(ValueError, match=r"Source|Result"):
        inspect_graph(broken, database, settings, OWNER)


def test_table_reflection_and_sql_discovery_with_in_process_database(env, monkeypatch):
    """Exercise real reflection and SQL locally; external dialect integration is separate."""
    from contextlib import contextmanager

    from langflow.business import connections
    from langflow.business.field_schema import sample_evidence
    from langflow.business.models import Connection
    from sqlalchemy import create_engine, text

    database, settings = env
    with database.sessions.begin() as session:
        source = Connection(owner_id=OWNER, kind="postgresql", name="Reflection fixture", config={})
        session.add(source)
        session.flush()
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as sql:
            sql.execute(text("ATTACH DATABASE ':memory:' AS audit"))
            sql.execute(text("CREATE TABLE main.records (code TEXT)"))
            sql.execute(text("CREATE TABLE audit.records (audit_code TEXT)"))

            @contextmanager
            def fixture_connection(*_args):
                yield sql

            monkeypatch.setattr(connections, "readonly", fixture_connection)
            assert "audit" in connections.metadata(source, settings)["schemas"]
            assert connections.metadata(source, settings, "records", "")["fields"][0]["name"] == "code"
            assert connections.metadata(source, settings, "records", "main")["fields"][0]["name"] == "code"
            assert connections.metadata(source, settings, "records", "audit")["fields"][0]["name"] == "audit_code"
            config = {
                "connection": source.id,
                "table": "records",
                "schema": "audit",
                "conditions": [{"field": "code", "op": "eq", "value": "A"}],
            }
            graph = {
                "nodes": [
                    {"id": "Source", "kind": "database", "config": config},
                    {"id": "Result", "kind": "output", "config": {"name": "Result"}},
                ],
                "edges": [{"source": "Source", "target": "Result", "port": "data", "input": "data"}],
            }
            with pytest.raises(ValueError, match="Unavailable field"):
                inspect_graph(graph, database, settings, OWNER)
            config["conditions"][0]["field"] = "audit_code"
            assert (
                inspect_graph(graph, database, settings, OWNER)["schemas"]["Source"]["data"][0]["name"] == "audit_code"
            )
            config.clear()
            config.update(connection=source.id, sql="SELECT code AS external_id FROM main.records")
            result = connections.preview(source, settings, config, {})
            assert result["rows"] == []
            assert result["fields"][0]["name"] == "external_id"
            assert result["uncertain_types"] == ["external_id"]
            config["fields"] = [{"name": "external_id", "type": "text"}]
            config["field_evidence"] = sample_evidence(config, result["fields"], source, settings, OWNER)
            assert (
                inspect_graph(graph, database, settings, OWNER)["schemas"]["Source"]["data"][0]["name"] == "external_id"
            )
            config["sql"] = "SELECT 'A' AS renamed"
            with pytest.raises(ValueError, match="changed"):
                inspect_graph(graph, database, settings, OWNER)
    finally:
        engine.dispose()
