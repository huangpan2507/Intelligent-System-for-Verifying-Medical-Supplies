# ruff: noqa: INP001, RUF001, T201 - standalone local deployment CLI with Chinese canvas names.
"""Prepare or create a separate eleven-node core canvas, preserving the original canvas and releases."""

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from langflow.business.compiler import inspect_graph, runtime_digest
from langflow.business.components import from_langflow
from langflow.business.connections import metadata
from langflow.business.maintenance import status
from langflow.business.models import Connection
from langflow.verification.database import Database
from langflow.verification.settings import VerificationSettings

from scripts.business.apply_core_classification import FLOW, call, save
from scripts.business.build_compact_core import build_graph

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "deploy/business/evidence/core-compact-20261014"
SCHEME = "core.normal.compact.v1"
NAME = "髋膝关节正常核心流程（数据库＋API，精简11节点）"


def local_context():
    private = dotenv_values(ROOT / "deploy/verification/.env")
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
    return private, Database(url, "verification_scope"), settings


def login(http, private):
    result = call(
        http,
        "POST",
        "/api/v1/login",
        data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
    )
    http.headers["Authorization"] = "Bearer " + result["access_token"]
    return call(http, "GET", "/api/v1/users/whoami")["id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    private, db, settings = local_context()
    try:
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            original = call(http, "GET", f"/api/v1/flows/{FLOW}")
            graph = from_langflow(original["data"])
            source = next(n for n in graph["nodes"] if n["label"] == "Settlements")["config"]
            with db.sessions() as session:
                connection = session.get(Connection, source["connection"])
            fields = metadata(connection, settings, source["table"], source.get("schema"))["fields"]
            graph = build_graph(graph, [f["name"] for f in fields])
            package = inspect_graph(graph, db, settings, owner, strict=False)
            save(EVIDENCE / "preflight.json", {"nodes": len(graph["nodes"]), "errors": package["errors"]})
            save(EVIDENCE / "graph.json", graph)
            print(
                json.dumps({"nodes": len(graph["nodes"]), "errors": package["errors"]}, ensure_ascii=False), flush=True
            )
            if package["errors"]:
                raise SystemExit(1)
            if not args.apply:
                return
            if not status(db)["safe_to_upgrade"]:
                msg = "Pause local intake and drain accepted work before activation"
                raise ValueError(msg)
            schemes = call(http, "GET", "/api/v1/business/schemes")
            current = next((s for s in schemes if s["code"] == SCHEME), None)
            if current is None:
                current = call(
                    http,
                    "POST",
                    "/api/v1/business/schemes",
                    json={"code": SCHEME, "name": NAME, "graph": graph, "allowed_sources": ["demo-regulator"]},
                )
            else:
                saved = call(http, "GET", f"/api/v1/flows/{current['flow_id']}")
                if from_langflow(saved["data"]) != graph:
                    msg = "The existing compact canvas differs; review changes before replacing it"
                    raise ValueError(msg)
            # Runtime fingerprints are immutable; upgrade active versions from their saved packages, not drafts.
            schemes = call(http, "GET", "/api/v1/business/schemes")
            upgrades = []
            for scheme in schemes:
                code = scheme["code"]
                if code != SCHEME and not scheme["active_release_id"]:
                    continue
                releases = call(http, "GET", f"/api/v1/business/schemes/{code}/releases")
                active = next((r for r in releases if r["id"] == scheme["active_release_id"]), None)
                if active and active["package"]["runtime_digest"] == runtime_digest():
                    continue
                suffix = "" if code == SCHEME else f"/from/{active['id']}"
                release = call(
                    http,
                    "POST",
                    f"/api/v1/business/schemes/{code}/releases{suffix}",
                    json={
                        "expected_revision": scheme["revision"],
                        "note": "Reusable compact capabilities; existing graphs preserved",
                    },
                )
                revision = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == code)[
                    "revision"
                ]
                call(
                    http,
                    "PUT",
                    f"/api/v1/business/schemes/{code}/active",
                    json={"expected_revision": revision, "release_id": release["id"]},
                )
                upgrades.append({"scheme": code, "release_id": release["id"], "version": release["version"]})
            if call(http, "GET", f"/api/v1/flows/{FLOW}")["data"] != original["data"]:
                msg = "Original canvas changed during the upgrade"
                raise ValueError(msg)
            save(
                EVIDENCE / "deployment.json",
                {
                    "scheme": SCHEME,
                    "flow_id": current["flow_id"],
                    "original_flow_id": FLOW,
                    "original_canvas_unchanged": True,
                    "releases": upgrades,
                },
            )
            print(json.dumps({"flow_id": current["flow_id"], "scheme": SCHEME, "releases": upgrades}), flush=True)
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
