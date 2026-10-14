"""Dedicated SQL source fixtures for the million-row acceptance command."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import Column, MetaData, Numeric, String, Table, create_engine
from sqlalchemy.engine import URL

from langflow.business.connections import encrypt
from langflow.business.models import Connection
from langflow.business.templates import comparison


def prepare_sources(database, settings, owner, count):
    password = dotenv_values(Path("deploy/verification/.cache/business-sources.env"))["BUSINESS_DB_PASSWORD"]
    suffix = uuid4().hex[:12]
    resources = []
    connections, names = {}, {}

    def cleanup():
        for table, engine in resources:
            try:
                table.drop(engine, checkfirst=True)
            finally:
                engine.dispose()

    try:
        for role, kind, driver, port in [
            ("orders", "mysql", "mysql+pymysql", 13306),
            ("payments", "postgresql", "postgresql+psycopg", 55434),
        ]:
            config = {"host": "127.0.0.1", "port": port, "username": "business_demo", "database": "business_demo"}
            with database.sessions.begin() as session:
                connection = Connection(
                    owner_id=owner,
                    name=f"Benchmark {role}",
                    kind=kind,
                    config=config,
                    secret=encrypt(password, settings),
                )
                session.add(connection)
                session.flush()
            connections[role] = connection.id
            engine = create_engine(
                URL.create(
                    driver,
                    username=config["username"],
                    password=password,
                    host=config["host"],
                    port=port,
                    database=config["database"],
                )
            )
            columns = (
                [Column("order_no", String(40), primary_key=True)]
                if role == "orders"
                else [Column("payment_id", String(40), primary_key=True), Column("biz_no", String(40))]
            ) + [Column("amount", Numeric(20, 2)), Column("unused_original_field", String(50))]
            table = Table(f"benchmark_{role}_{suffix}", MetaData(), *columns)
            table.create(engine)
            resources.append((table, engine))
            names[role] = table.name
            with engine.begin() as sql:
                for offset in range(0, count, 5000):
                    rows = []
                    for i in range(offset, min(offset + 5000, count)):
                        row = {
                            "amount": Decimal(99 if role == "payments" and i % 10000 == 0 else 100),
                            "unused_original_field": "raw-preserved",
                        }
                        row.update(
                            {"order_no": f"O{i}"} if role == "orders" else {"payment_id": f"P{i}", "biz_no": f"O{i}"}
                        )
                        rows.append(row)
                    sql.execute(table.insert(), rows)
            print(f"Prepared {count} rows in {kind} ({role})", flush=True)
        graph = comparison(connections)
        for node in graph["nodes"]:
            if node["id"] == "Orders":
                node["config"]["table"] = names["orders"]
            elif node["id"] == "Payments":
                node["config"]["table"] = names["payments"]
        return graph, cleanup
    except BaseException:
        cleanup()
        raise
