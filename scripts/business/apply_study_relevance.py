# ruff: noqa: RUF001 - approved Chinese canvas name.
"""Upgrade the local core canvas and owned synthetic database records while intake is paused."""

import json

import httpx
from dotenv import dotenv_values
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow, to_langflow
from langflow.business.maintenance import status
from langflow.business.models import Scheme
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.engine import URL

from scripts.business.apply_compact_core import ROOT, SCHEME, local_context, login
from scripts.business.apply_core_classification import call, save
from scripts.business.prepare_core_database_sources import HOSPITAL, definitions, rows_for, seed
from scripts.business.study_relevance import configure_graph

EVIDENCE = ROOT / "deploy/business/evidence/study-relevance-20261014"
BACKUP = ROOT / "deploy/verification/.cache/study-relevance-20261014"
NAME = "髋膝关节正常核心流程（数据库＋API，精简11节点）"


def main():
    private, database, settings = local_context()
    engines = []
    try:
        if not status(database)["safe_to_upgrade"]:
            msg = "Pause intake and drain accepted work before this explicit local upgrade"
            raise ValueError(msg)
        password = dotenv_values(ROOT / "deploy/verification/.cache/business-sources.env")["BUSINESS_DB_PASSWORD"]
        engines = [
            create_engine(
                URL.create(
                    driver,
                    username="business_demo",
                    password=password,
                    host="127.0.0.1",
                    port=port,
                    database="business_demo",
                ),
                hide_parameters=True,
            )
            for driver, port in [("mysql+pymysql", 13306), ("postgresql+psycopg", 55434)]
        ]
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            scheme = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == SCHEME)
            path = f"/api/v1/flows/{scheme['flow_id']}"
            original = call(http, "GET", path)
            if not (BACKUP / "canvas.json").exists():
                save(BACKUP / "canvas.json", original)
                for name in ["INSPECTION_INFO_RECORD", "SERIES_INFO"]:
                    table = Table(name, MetaData(), autoload_with=engines[0])
                    with engines[0].connect() as db:
                        rows = [
                            dict(r) for r in db.execute(select(table).where(table.c.organ_code == HOSPITAL)).mappings()
                        ]
                    save(BACKUP / (name + ".json"), rows)
            tables, _ = definitions()
            seed(*engines, tables, rows_for(tables))
            graph = configure_graph(from_langflow(original["data"]))
            package = inspect_graph(graph, database, settings, owner, strict=False)
            save(EVIDENCE / "preflight.json", {"node_count": len(graph["nodes"]), "errors": package["errors"]})
            if package["errors"]:
                print(json.dumps(package["errors"], ensure_ascii=False))
                raise SystemExit(1)
            call(http, "PATCH", path, json={"name": NAME, "data": to_langflow(graph)})
            saved = from_langflow(call(http, "GET", path)["data"])
            def edge_set(spec):
                return {tuple(sorted(edge.items())) for edge in spec["edges"]}
            if saved["nodes"] != graph["nodes"] or edge_set(saved) != edge_set(graph):
                msg = "Saved canvas differs from the validated eleven-node graph"
                raise ValueError(msg)
            with database.sessions.begin() as session:
                current = session.get(Scheme, SCHEME)
                current.name = NAME
            save(EVIDENCE / "graph.json", graph)
            report = {
                "flow_id": scheme["flow_id"],
                "scheme": SCHEME,
                "node_count": len(graph["nodes"]),
                "source_rows": {name: len(rows) for name, rows in rows_for(tables).items()},
                "activation": "pending_restart_and_publish",
            }
            save(EVIDENCE / "deployment.json", report)
            print(json.dumps(report, ensure_ascii=False))
    finally:
        database.engine.dispose()
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
