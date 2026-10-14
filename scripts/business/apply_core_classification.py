# ruff: noqa: RUF001, S101 - local migration assertions and synthetic Chinese fixtures.
"""Inspect/apply the agreed core canvas while local task intake is paused.

Credentials are read only from existing local configuration. Backups preserve the
old canvas and the two explicitly named synthetic source rows. No real source is written.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from langflow.business.compiler import inspect_graph, runtime_digest
from langflow.business.components import from_langflow, to_langflow
from langflow.business.connections import preview
from langflow.business.maintenance import status
from langflow.business.models import Connection, Scheme
from langflow.verification.database import Database
from langflow.verification.settings import VerificationSettings
from sqlalchemy import MetaData, Table, create_engine, select, update
from sqlalchemy.engine import URL

from scripts.business.core_classification import build_graph

ROOT = Path(__file__).resolve().parents[2]
FLOW = "e55b03b0-7c7f-420b-b720-33b1a4cf5559"
SCHEME = "core.normal.1791804428546"
CONNECTIONS = {
    "settlements": "537d8c03-3c9a-4c25-8a8e-d66cfc2b187a",
    "imaging_db": "fb22b9dd-11b7-4650-b86d-78332de3e2ec",
    "images": "bd965b78-e1c6-4553-b884-c78a807b67bc",
    "model": "73f76ea6-93d7-48a3-8fcc-e33a406d0e29",
}
EVIDENCE = ROOT / "deploy/business/evidence/core-classification-20261014"
BACKUP = ROOT / "deploy/verification/.cache/core-classification-20261014"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def call(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def update_fixtures(password):
    """Idempotently migrate only two agreed, MOCK-prefixed records."""
    fixture = ROOT / "deploy/business/fixtures/core-flow/settlement-rows.json"
    data = json.loads(fixture.read_text())
    engines = [
        create_engine(
            URL.create(
                driver,
                username="business_demo",
                password=password,
                host="127.0.0.1",
                port=port,
                database="business_demo",
            )
        )
        for driver, port in [("postgresql+psycopg", 55434), ("mysql+pymysql", 13306)]
    ]
    try:
        settlement = Table("core_flow_settlement_v1", MetaData(), autoload_with=engines[0], schema="public")
        inspection = Table("INSPECTION_INFO_RECORD", MetaData(), autoload_with=engines[1])
        for joint, part, product in [
            ("HIP", "髋", "人工髋关节（模拟A型号）"),
            ("KNEE", "膝", "膝关节假体系统（模拟成套产品B）"),
        ]:
            row = next(r for r in data["rows"] if r["SETL_FEE_LIST_ID"] == "MOCK-DETAIL-" + joint)
            changes = {
                "HILIST_NAME": f"人工全{part}关节置换术",
                "PRODNAME": product,
                "HOS_PROJ_NAME": product,
                "MEDINS_LIST_NAME": product,
                "OP_EM_MARK": "3" if joint == "HIP" else "1",
            }
            condition = (row["SETL_FEE_LIST_ID"] == settlement.c.SETL_FEE_LIST_ID) & (
                settlement.c.ORGAN_CODE == "MOCKHOSP0000000001"
            )
            with engines[0].begin() as db:
                old = dict(db.execute(select(settlement).where(condition)).mappings().one())
                original_product = f"人工{part}关节（模拟{'A' if joint == 'HIP' else 'B'}型号）"
                assert old["HILIST_NAME"] in {original_product, changes["HILIST_NAME"]}, "Unexpected source edit"
                assert old["CNT"] == 1
                assert old["PRIC"] == (10000 if joint == "HIP" else 5000)
                backup = BACKUP / f"settlement-{joint}.json"
                if not backup.exists():
                    save(backup, old)
                db.execute(update(settlement).where(condition).values(**changes))
            row.update(changes)
        with engines[1].begin() as db:
            condition = (
                (inspection.c.organ_code == "MOCKHOSP0000000001")
                & (inspection.c.system_id == "MOCK-RIS01")
                & (inspection.c.ris_study_id == "MOCK-RIS-KNEE")
            )
            old = dict(db.execute(select(inspection).where(condition)).mappings().one())
            assert old["op_em_hp_ex_mark"] in {1, 3}
            backup = BACKUP / "inspection-KNEE.json"
            if not backup.exists():
                save(backup, old)
            db.execute(update(inspection).where(condition).values(op_em_hp_ex_mark=1))
        data["classification_source"] = (
            "HILIST_NAME is the source-provided surgery name; classify corresponding material facts using "
            "explicit rules plus a real text model for unresolved names. CNT/PRIC remain original."
        )
        save(fixture, data)
        path = ROOT / "deploy/business/fixtures/core-flow/database-sources/rows.json"
        imaging = json.loads(path.read_text())
        for row in imaging["tables"]["INSPECTION_INFO_RECORD"]:
            if row["ris_study_id"] == "MOCK-RIS-KNEE":
                row["op_em_hp_ex_mark"] = 1
        save(path, imaging)
    finally:
        for engine in engines:
            engine.dispose()


def allow_mock_regulator(db, owner):
    """Enable the configured local simulator on this owned core scheme only."""
    with db.sessions.begin() as session:
        scheme = session.get(Scheme, SCHEME, with_for_update=True)
        assert scheme.owner_id == owner
        if "demo-regulator" not in scheme.allowed_sources:
            save(BACKUP / "allowed-sources-before.json", {"scheme": SCHEME, "sources": scheme.allowed_sources})
            scheme.allowed_sources = [*scheme.allowed_sources, "demo-regulator"]
            scheme.revision += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    sources = dotenv_values(ROOT / "deploy/verification/.cache/business-sources.env")
    url = (
        "postgresql+psycopg://verification_app:"
        + quote(private["VERIFICATION_DB_PASSWORD"], safe="")
        + "@127.0.0.1:55433/verification"
    )
    settings = VerificationSettings(
        database_url=url,
        database_schema="verification_scope",
        internal_token=private["VERIFICATION_INTERNAL_TOKEN"],
        clients=json.loads(private["VERIFICATION_CLIENTS"]),
        demo_mode=True,
    )
    db = Database(url, "verification_scope")
    try:
        if args.apply:
            assert status(db)["safe_to_upgrade"], "Pause intake and drain tasks first"
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            login = call(
                http,
                "POST",
                "/api/v1/login",
                data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
            )
            http.headers["Authorization"] = "Bearer " + login["access_token"]
            owner = call(http, "GET", "/api/v1/users/whoami")["id"]
            path = f"/api/v1/flows/{FLOW}"
            flow = call(http, "GET", path)
            graph = build_graph(from_langflow(flow["data"]), CONNECTIONS)
            package = inspect_graph(graph, db, settings, owner, strict=False)
            save(
                EVIDENCE / "preflight.json",
                {"nodes": len(graph["nodes"]), "errors": package["errors"], "runtime_digest": runtime_digest()},
            )
            print(
                json.dumps({"nodes": len(graph["nodes"]), "errors": package["errors"]}, ensure_ascii=False), flush=True
            )
            if package["errors"]:
                raise SystemExit(1)
            # Schema inspection alone cannot catch a numeric column bound as VARCHAR.
            parameters = {
                "hospital_name": "核心流程模拟医院",
                "start": "2025-08-01 00:00:00",
                "end": "2025-08-31 23:59:59",
            }
            for node in graph["nodes"]:
                if node["kind"] == "database":
                    with db.sessions() as session:
                        connection = session.get(Connection, node["config"]["connection"])
                    preview(connection, settings, node["config"], parameters)
            if not args.apply:
                return
            assert "demo-regulator" in settings.clients
            allow_mock_regulator(db, owner)
            backup = BACKUP / "canvas-before.json"
            if not backup.exists():
                save(backup, flow)
            update_fixtures(sources["BUSINESS_DB_PASSWORD"])
            canvas = to_langflow(graph, flow["name"])
            assert call(http, "GET", path)["data"] == flow["data"], "Canvas changed concurrently"
            call(http, "PATCH", path, json={"data": canvas})
            assert call(http, "GET", path)["data"] == canvas
            save(EVIDENCE / "graph.json", graph)
            schemes = call(http, "GET", "/api/v1/business/schemes")
            upgrades = []
            for scheme in schemes:
                code = scheme["code"]
                if code != SCHEME and not scheme["active_release_id"]:
                    continue
                releases = call(http, "GET", f"/api/v1/business/schemes/{code}/releases")
                active = next((r for r in releases if r["id"] == scheme["active_release_id"]), None)
                if code != SCHEME and active["package"]["runtime_digest"] == runtime_digest():
                    continue
                suffix = "" if code == SCHEME else f"/from/{active['id']}"
                release = call(
                    http,
                    "POST",
                    f"/api/v1/business/schemes/{code}/releases{suffix}",
                    json={
                        "expected_revision": scheme["revision"],
                        "note": "Core classification / compatible runtime upgrade; synthetic local sources",
                    },
                )
                current = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == code)
                call(
                    http,
                    "PUT",
                    f"/api/v1/business/schemes/{code}/active",
                    json={"expected_revision": current["revision"], "release_id": release["id"]},
                )
                upgrades.append({"scheme": code, "release_id": release["id"], "version": release["version"]})
            save(EVIDENCE / "releases.json", upgrades)
            print(json.dumps({"applied_flow": FLOW, "releases": upgrades}, ensure_ascii=False), flush=True)
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
