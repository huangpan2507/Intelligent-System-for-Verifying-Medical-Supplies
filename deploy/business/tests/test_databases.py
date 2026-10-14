"""Real source integration: opt in after starting deploy/business/compose.yaml."""

import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import dotenv_values
from sqlalchemy import Column, MetaData, Numeric, String, Table, select, text
from sqlalchemy.engine import URL, create_engine

from langflow.business.connections import encrypt, preview, readonly
from langflow.business.models import Connection
from langflow.business.templates import comparison
from test_workflows import OWNER, env, execute_release, save_release, upstream

pytestmark = pytest.mark.skipif(
    os.getenv("BUSINESS_REAL_DATABASES") != "1",
    reason="Start dedicated MySQL/PostgreSQL sources and set BUSINESS_REAL_DATABASES=1",
)


def test_configuration_discovery_distinguishes_schemas_and_sql_aliases(env, sources):
    from langflow.business.compiler import inspect_graph
    from langflow.business.connections import metadata
    from langflow.business.field_schema import sample_evidence

    database, settings = env
    connection, engine = sources["postgresql"]
    suffix = uuid4().hex[:10]
    schemas = [f"fields_a_{suffix}", f"fields_b_{suffix}"]
    try:
        with engine.begin() as sql:
            for index, schema in enumerate(schemas):
                sql.execute(text(f'CREATE SCHEMA "{schema}"'))
                sql.execute(text(f'CREATE TABLE "{schema}".records ("code_{index}" TEXT)'))
        for index, schema in enumerate(schemas):
            assert metadata(connection, settings, schema=schema)["tables"] == ["records"]
            assert [f["name"] for f in metadata(connection, settings, "records", schema)["fields"]] == [f"code_{index}"]
        config = {"connection": connection.id, "schema": schemas[0], "table": "records",
                  "conditions": [{"field": "invented", "op": "eq", "value": "A"}]}
        graph = {"nodes": [{"id": "Source", "kind": "database", "config": config},
                           {"id": "Result", "kind": "output", "config": {"name": "Result"}}],
                 "edges": [{"source": "Source", "target": "Result", "port": "data", "input": "data"}]}
        with pytest.raises(ValueError, match="invented"):
            inspect_graph(graph, database, settings, OWNER)
        config.clear()
        config.update(connection=connection.id, sql=f'SELECT code_0 AS external_id FROM "{schemas[0]}".records')
        result = preview(connection, settings, config, {})
        assert result["rows"] == []
        assert result["fields"][0]["name"] == "external_id"
        config["fields"] = [{"name": "external_id", "type": "text"}]
        config["field_evidence"] = sample_evidence(config, result["fields"], connection, settings, OWNER)
        assert inspect_graph(graph, database, settings, OWNER)["schemas"]["Source"]["data"][0]["name"] == "external_id"
        config["sql"] = "SELECT 'A' AS renamed"
        with pytest.raises(ValueError, match="changed"):
            inspect_graph(graph, database, settings, OWNER)
    finally:
        with engine.begin() as sql:
            for schema in schemas:
                sql.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture
def sources(env):
    database, settings = env
    secret = dotenv_values(Path("deploy/verification/.cache/business-sources.env"))["BUSINESS_DB_PASSWORD"]
    entries = {}
    for kind, port, driver in [("mysql", 13306, "mysql+pymysql"), ("postgresql", 55434, "postgresql+psycopg")]:
        with database.sessions.begin() as session:
            connection = Connection(
                owner_id=OWNER,
                name=kind,
                kind=kind,
                config={"host": "127.0.0.1", "port": port, "username": "business_demo", "database": "business_demo"},
                secret=encrypt(secret, settings),
            )
            session.add(connection)
            session.flush()
        engine = create_engine(
            URL.create(
                driver, username="business_demo", password=secret, host="127.0.0.1", port=port, database="business_demo"
            )
        )
        entries[kind] = (connection, engine)
    yield entries
    for _, engine in entries.values():
        engine.dispose()


async def test_switch_connections_tables_and_field_names(env, sources):
    """Same executor, distinct schema names; counterpart payments cross the 5000-row batch boundary."""
    suffix = uuid4().hex[:10]
    orders = Table(
        f"acceptance_orders_{suffix}",
        MetaData(),
        Column("external_key", String(30), primary_key=True),
        Column("expected_value", Numeric(24, 8)),
        Column("unused", String(50)),
    )
    payments = Table(
        f"acceptance_payments_{suffix}",
        MetaData(),
        Column("entry_key", String(30), primary_key=True),
        Column("reference_key", String(30)),
        Column("observed_value", Numeric(24, 8)),
    )
    mysql, mysql_engine = sources["mysql"]
    postgres, postgres_engine = sources["postgresql"]
    orders.create(mysql_engine)
    payments.create(postgres_engine)
    try:
        with mysql_engine.begin() as db:
            db.execute(
                orders.insert(),
                [
                    {"external_key": "A", "expected_value": Decimal("5001.00000001"), "unused": "full raw fields"},
                    {"external_key": "B", "expected_value": Decimal("3.00000001"), "unused": "full raw fields"},
                    {"external_key": "C", "expected_value": 8, "unused": "full raw fields"},
                ],
            )
        with postgres_engine.begin() as db:
            db.execute(
                payments.insert(),
                [
                    {
                        "entry_key": str(i),
                        "reference_key": "A",
                        "observed_value": Decimal("1.00000001") if i == 5000 else Decimal(1),
                    }
                    for i in range(5001)
                ],
            )
            db.execute(
                payments.insert(),
                [
                    {"entry_key": "B", "reference_key": "B", "observed_value": Decimal("3.00000002")},
                    {"entry_key": "D", "reference_key": "D", "observed_value": 4},
                ],
            )
        graph = comparison({"orders": mysql.id, "payments": postgres.id})
        replacements = {
            "order_no": "external_key",
            "payment_id": "entry_key",
            "biz_no": "reference_key",
            "left_amount": "left_expected_value",
        }
        import json

        serialized = json.dumps(graph)
        for old, new in replacements.items():
            serialized = serialized.replace('"' + old + '"', '"' + new + '"')
        graph = json.loads(serialized)
        for node in graph["nodes"]:
            if node["id"] == "Orders":
                node["config"]["table"] = orders.name
            elif node["id"] == "Payments":
                node["config"]["table"] = payments.name
            elif node["id"] == "OrderChecks":
                node["config"]["required"] = ["external_key", "expected_value"]
            elif node["id"] == "PaymentChecks":
                node["config"]["required"] = ["entry_key", "reference_key", "observed_value"]
            elif node["id"] == "PaymentTotals":
                node["config"]["metrics"][0]["field"] = "observed_value"
        runtime = await execute_release(env, save_release(env, graph))
        result = runtime.store.page(runtime.outputs["Results"]["data"]["id"])["rows"]
        assert {r["_comparison_status"] for r in result} == {"equal", "different", "left_only", "right_only"}
        different = next(r for r in result if r["_comparison_status"] == "different")
        assert Decimal(different["difference_0"]) == Decimal("0.00000001")
        assert runtime.store.page(runtime.outputs["Orders"]["data"]["id"])["rows"][0]["unused"] == "full raw fields"
        sample = preview(mysql, env[1], {"table": orders.name}, {})
        assert len(sample["rows"]) == 3
        # Verify source writes are denied even when the configured DB account has DDL rights.
        for connection, table in [(mysql, orders), (postgres, payments)]:
            with pytest.raises(Exception):
                with readonly(connection, env[1]) as db:
                    db.execute(text(f"DELETE FROM {table.name}"))
    finally:
        orders.drop(mysql_engine)
        payments.drop(postgres_engine)


async def test_database_and_paginated_api_use_the_same_comparison_graph(env, sources, upstream):
    mysql, engine = sources["mysql"]
    orders = Table(f"mixed_orders_{uuid4().hex[:10]}", MetaData(), Column("order_no", String(30), primary_key=True),
                   Column("amount", Numeric(20, 2)))
    orders.create(engine)
    try:
        with engine.begin() as sql:
            sql.execute(orders.insert(), [{"order_no": "O001", "amount": 100}, {"order_no": "O002", "amount": 200}])
        graph = comparison({"orders": mysql.id})
        for node in graph["nodes"]:
            if node["id"] == "Orders":
                node["config"]["table"] = orders.name
            if node["id"] == "Payments":
                node.update(kind="api", config={"connection": upstream.id, "path": "/comparison-payments",
                    "items_path": "items", "pagination": "page", "fields": [
                        {"name": "payment_id", "type": "text"}, {"name": "biz_no", "type": "text"},
                        {"name": "amount", "type": "number", "scale": 2}],
                    "completeness": {"scope": "range", "basis": "Test protocol: exhaust pages to empty response"}})
                from langflow.business.field_schema import document_evidence

                node["config"]["field_evidence"] = document_evidence(
                    node["config"], node["config"]["fields"], "Test fixture /comparison-payments response contract"
                )
        runtime = await execute_release(env, save_release(env, graph))
        assert not runtime.failures
        rows = runtime.store.page(runtime.outputs["Results"]["data"]["id"])["rows"]
        assert {row["left_order_no"]: row["_comparison_status"] for row in rows} == {"O001": "equal", "O002": "different"}
    finally:
        orders.drop(engine)


def test_default_schema_is_reported_by_each_database(env, sources):
    from langflow.business.connections import metadata

    _, settings = env
    for kind, expected in [("postgresql", "public"), ("mysql", "business_demo")]:
        result = metadata(sources[kind][0], settings)
        assert result["default_schema"] == expected
        assert expected in result["schemas"]
