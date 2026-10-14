# ruff: noqa: INP001, S101, F811 - standalone pytest suite with shared fixtures.
"""Normal core-path regressions: typed dates, literal URLs and real canvas inputs."""

import os
from datetime import datetime
from uuid import uuid4

import duckdb
import pytest
from langflow.business.compiler import sql_type
from langflow.business.components import from_langflow, to_langflow
from langflow.business.connections import metadata, preview
from langflow.business.expressions import expression
from sqlalchemy import Column, DateTime, Integer, MetaData, Table
from test_databases import sources  # noqa: F401
from test_workflows import env, execute_release, save_release  # noqa: F401


def test_concat_preserves_signed_image_path_and_explicit_check_timezone():
    fields = ["domain", "file_path", "chk_dt"]
    address = expression("concat(domain, file_path)", fields)
    check = expression("concat(chk_dt, '+08:00')", fields)
    with duckdb.connect() as db:
        db.execute("SET TimeZone='UTC'")
        row = db.execute(
            f"SELECT {address}, CAST({check} AS TIMESTAMPTZ) "  # noqa: S608 - compiled expressions, bound source values.
            "FROM (SELECT ? AS domain, ? AS file_path, ? AS chk_dt)",
            ["https://dicom.invalid", "/a.dcm?signature=x%2Fy&expires=0", "2025-08-20 09:00:00"],
        ).fetchone()
    assert row[0] == "https://dicom.invalid/a.dcm?signature=x%2Fy&expires=0"
    assert row[1].isoformat() == "2025-08-20T01:00:00+00:00"


def test_canvas_inputs_match_node_roles_and_keep_parameter_dependency():
    kinds = ["parameters", "database", "file", "transform", "join", "union", "api", "imaging", "output"]
    spec = {
        "nodes": [{"id": kind.title(), "kind": kind} for kind in kinds],
        "edges": [{"source": "Parameters", "target": "Database", "port": "data", "input": "data"}],
    }
    canvas = to_langflow(spec)
    expected = {
        "parameters": [],
        "database": ["input_data"],
        "file": [],
        "transform": ["input_data"],
        "join": ["input_left", "input_right"],
        "union": ["input_data"],
        "api": ["input_data"],
        "imaging": ["input_data"],
        "output": ["input_data"],
    }
    for node in canvas["nodes"]:
        template = node["data"]["node"]["template"]
        kind = template["_business_kind"]["value"]
        handles = [
            key
            for key, value in template.items()
            if key.startswith("input_") and value.get("show") and not value.get("advanced")
        ]
        assert handles == expected[kind]
        if kind == "database":
            assert template["input_data"]["display_name"] == "Parameters"
        if kind in {"transform", "union"}:
            assert template["input_data"]["list"] == (kind == "union")
    assert from_langflow(canvas)["edges"] == spec["edges"]


@pytest.mark.skipif(os.getenv("BUSINESS_REAL_DATABASES") != "1", reason="Requires dedicated source PostgreSQL")
async def test_local_task_dates_read_timezone_column_without_schema_drift(env, sources):
    connection, engine = sources["postgresql"]
    table = Table(
        f"core_dates_{uuid4().hex[:10]}",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("settled_at", DateTime(timezone=True), nullable=False),
    )
    table.create(engine)
    try:
        with engine.begin() as db:
            db.execute(
                table.insert(),
                [
                    {"id": 1, "settled_at": datetime.fromisoformat("2025-07-31T23:59:59+08:00")},
                    {"id": 2, "settled_at": datetime.fromisoformat("2025-08-01T00:00:00+08:00")},
                    {"id": 3, "settled_at": datetime.fromisoformat("2025-08-31T23:59:59+08:00")},
                    {"id": 4, "settled_at": datetime.fromisoformat("2025-09-01T00:00:00+08:00")},
                ],
            )
        config = {
            "connection": connection.id,
            "table": table.name,
            "timezone": "Asia/Shanghai",
            "conditions": [
                {"field": "settled_at", "op": "ge", "parameter": "start"},
                {"field": "settled_at", "op": "le", "parameter": "end"},
            ],
        }
        parameters = {"start": "2025-08-01 00:00:00", "end": "2025-08-31 23:59:59"}
        result = preview(connection, env[1], config, parameters)
        assert {row["id"] for row in result["rows"]} == {2, 3}
        for fields in [result["fields"], metadata(connection, env[1], table.name)["fields"]]:
            assert sql_type(next(f["type"] for f in fields if f["name"] == "settled_at")) == "TIMESTAMPTZ"
        graph = {
            "nodes": [
                {
                    "id": "Request",
                    "kind": "parameters",
                    "config": {"parameters": [{"name": key, "type": "string", "required": True} for key in parameters]},
                },
                {"id": "Database", "kind": "database", "config": config},
                {"id": "Result", "kind": "output", "config": {"name": "Result"}},
            ],
            "edges": [
                {"source": "Request", "target": "Database", "port": "data", "input": "data"},
                {"source": "Database", "target": "Result", "port": "data", "input": "data"},
            ],
        }
        runtime = await execute_release(env, save_release(env, graph), parameters)
        assert not runtime.failures
        assert {r["id"] for r in runtime.store.page(runtime.outputs["Result"]["data"]["id"])["rows"]} == {2, 3}
    finally:
        table.drop(engine)
