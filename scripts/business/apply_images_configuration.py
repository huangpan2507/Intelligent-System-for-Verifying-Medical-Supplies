# ruff: noqa: S101, PLR2004 - local, explicitly requested canvas acceptance.
"""Add the application number to image context without replacing the live canvas."""

import copy
import json

import httpx
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow
from langflow.business.maintenance import status

from scripts.business.apply_compact_core import ROOT, SCHEME, local_context, login
from scripts.business.apply_core_classification import call, save

EVIDENCE = ROOT / "deploy/business/evidence/images-configuration-20261015"


def main():
    private, database, settings = local_context()
    try:
        if not status(database)["safe_to_upgrade"]:
            message = "Pause intake and drain accepted tasks before updating this canvas"
            raise ValueError(message)
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            scheme = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == SCHEME)
            path = f"/api/v1/flows/{scheme['flow_id']}"
            original = call(http, "GET", path)
            backup = ROOT / "deploy/verification/.cache/images-configuration-20261015/canvas.json"
            if not backup.exists():
                save(backup, original)
            canvas = copy.deepcopy(original["data"])
            node = next(n for n in canvas["nodes"] if n["id"] == "Images")
            field = node["data"]["node"]["template"]["configuration"]
            config = json.loads(field["value"])
            retained = list(config["collection"]["retain_fields"])
            context = config["collection"].setdefault("item_context", [])
            if "RPT_NO" not in context:
                context.insert(0, "RPT_NO")
            field["value"] = json.dumps(config, ensure_ascii=False)
            graph = from_langflow(canvas)
            inspection = inspect_graph(graph, database, settings, owner, strict=False)
            save(EVIDENCE / "preflight.json", {"errors": inspection["errors"], "node_count": len(graph["nodes"])})
            assert not inspection["errors"], inspection["errors"]
            assert len(graph["nodes"]) == 11
            assert len(retained) == 58
            assert call(http, "GET", path)["data"] == original["data"], "Canvas changed while preparing update"
            call(http, "PATCH", path, json={"data": canvas})
            assert call(http, "GET", path)["data"] == canvas
            release = call(
                http,
                "POST",
                f"/api/v1/business/schemes/{SCHEME}/releases",
                json={
                    "expected_revision": scheme["revision"],
                    "note": "Images: include RPT_NO in per-image evidence context",
                },
            )
            current = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == SCHEME)
            call(
                http,
                "PUT",
                f"/api/v1/business/schemes/{SCHEME}/active",
                json={
                    "expected_revision": current["revision"],
                    "release_id": release["id"],
                },
            )
            report = {
                "flow_id": scheme["flow_id"],
                "release_id": release["id"],
                "version": release["version"],
                "node_count": 11,
                "retain_fields": retained,
                "item_context": context,
            }
            save(EVIDENCE / "deployment.json", report)
            print(json.dumps({k: v for k, v in report.items() if k not in {"retain_fields", "item_context"}}))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
