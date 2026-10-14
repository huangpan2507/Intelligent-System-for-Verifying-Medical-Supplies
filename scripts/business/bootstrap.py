"""Prepare isolated example data, create missing schemes, then drain legacy intake."""

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values
from langflow.business.compiler import runtime_digest
from langflow.business.templates import comparison, consumables
from sqlalchemy import Column, MetaData, Numeric, String, Table, create_engine, func, select
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]


def seed_sources(password):
    definitions = [
        (
            "mysql+pymysql",
            13306,
            "orders",
            [
                Column("order_no", String(80), primary_key=True),
                Column("amount", Numeric(20, 2)),
                Column("description", String(100)),
            ],
            [
                {"order_no": "O001", "amount": 100, "description": "Original field retained"},
                {"order_no": "O002", "amount": 200, "description": "Difference example"},
                {"order_no": "O003", "amount": 300, "description": "Order only"},
            ],
        ),
        (
            "postgresql+psycopg",
            55434,
            "payments",
            [
                Column("payment_id", String(80), primary_key=True),
                Column("biz_no", String(80)),
                Column("amount", Numeric(20, 2)),
                Column("channel", String(80)),
            ],
            [
                {"payment_id": "P01", "biz_no": "O001", "amount": 60, "channel": "example"},
                {"payment_id": "P02", "biz_no": "O001", "amount": 40, "channel": "example"},
                {"payment_id": "P03", "biz_no": "O002", "amount": 180, "channel": "example"},
                {"payment_id": "P04", "biz_no": "O004", "amount": 50, "channel": "example"},
            ],
        ),
    ]
    for driver, port, name, columns, rows in definitions:
        engine = create_engine(
            URL.create(
                driver,
                username="business_demo",
                password=password,
                host="127.0.0.1",
                port=port,
                database="business_demo",
            )
        )
        try:
            table = Table(name, MetaData(), *columns)
            table.create(engine, checkfirst=True)
            with engine.begin() as db:
                if db.scalar(select(func.count()).select_from(table)) == 0:
                    db.execute(table.insert(), rows)
        finally:
            engine.dispose()


def call(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    if not response.is_success:
        # Never print request bodies, which can contain connection credentials.
        msg = f"{method} {path}: HTTP {response.status_code}; check service logs"
        raise RuntimeError(msg)
    return response.json()


def main():
    private = dotenv_values(ROOT / "deploy/verification/.env")
    sources = dotenv_values(ROOT / "deploy/verification/.cache/business-sources.env")
    seed_sources(sources["BUSINESS_DB_PASSWORD"])
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
        login = call(
            http,
            "POST",
            "/api/v1/login",
            data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
        )
        http.headers["Authorization"] = "Bearer " + login["access_token"]
        user = call(http, "GET", "/api/v1/users/whoami")
        existing = call(http, "GET", "/api/v1/business/connections")
        ids = {}
        for key, name, kind, config, secret in [
            (
                "orders",
                "示例订单 MySQL",
                "mysql",
                {"host": "127.0.0.1", "port": 13306, "database": "business_demo", "username": "business_demo"},
                sources["BUSINESS_DB_PASSWORD"],
            ),
            (
                "payments",
                "示例付款 PostgreSQL",
                "postgresql",
                {"host": "127.0.0.1", "port": 55434, "database": "business_demo", "username": "business_demo"},
                sources["BUSINESS_DB_PASSWORD"],
            ),
            (
                "demo",
                "模拟结算、目录与影像服务",
                "api",
                {"base_url": "http://127.0.0.1:8090"},
                private["VERIFICATION_UPSTREAM_TOKEN"],
            ),
        ]:
            connection = next((c for c in existing if c["name"] == name), None)
            if connection is None:
                connection = call(
                    http,
                    "POST",
                    "/api/v1/business/connections",
                    json={"name": name, "kind": kind, "config": config, "secret": secret},
                )
            ids[key] = connection["id"]
        allowed = list(json.loads(private["VERIFICATION_CLIENTS"]))
        schemes = call(http, "GET", "/api/v1/business/schemes")
        for code, name, graph in [
            ("demo.cross_database.v2", "跨库对账（契约 v2，模拟业务数据）", comparison(ids)),
            ("demo.consumables.v2", "高值耗材核验（契约 v2，模拟）", consumables(ids["demo"])),
        ]:
            scheme = next((s for s in schemes if s["code"] == code), None)
            if scheme is None:
                scheme = call(
                    http,
                    "POST",
                    "/api/v1/business/schemes",
                    json={"code": code, "name": name, "graph": graph, "allowed_sources": allowed},
                )
            releases = call(http, "GET", f"/api/v1/business/schemes/{code}/releases")
            active = next((r for r in releases if r["id"] == scheme["active_release_id"]), None)
            if active and active["package"]["runtime_digest"] == runtime_digest():
                continue
            release = call(
                http,
                "POST",
                f"/api/v1/business/schemes/{code}/releases"
                + (f"/from/{active['id']}" if active else ""),
                json={
                    "expected_revision": scheme["revision"],
                    "note": "Generic platform example; synthetic business data",
                },
            )
            # Upgrade the active immutable configuration; only a new example publishes its draft.
            # Initial publication synchronizes the canvas and may increment its revision.
            scheme = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == code)
            call(
                http,
                "PUT",
                f"/api/v1/business/schemes/{code}/active",
                json={"expected_revision": scheme["revision"], "release_id": release["id"]},
            )
        # Preserve v1 canvases, immutable releases and task results. Only retire the built-in v1 examples.
        for scheme in schemes:
            if scheme["code"] in {"demo.cross_database", "demo.consumables"} and scheme["active_release_id"]:
                call(http, "PUT", f"/api/v1/business/schemes/{scheme['code']}/active",
                     json={"expected_revision": scheme["revision"], "release_id": None})
        api_port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{api_port}",
            timeout=30,
            headers={
                "Authorization": "Bearer " + private["VERIFICATION_INTERNAL_TOKEN"],
                "X-Business-Actor": user["id"],
            },
        ) as service:
            result = call(service, "POST", "/api/v1/business/internal/migration")
        if result["status"] != "complete":
            msg = f"Legacy intake stopped; {len(result['pending_runs'])} runs still need to finish or be confirmed. Historical records were preserved."
            raise RuntimeError(msg)
        print("Two generic schemes are active; legacy intake is closed and history is preserved.")


if __name__ == "__main__":
    main()
