"""Save the reviewed Lookup source bindings on the existing local core canvas."""

import json
from copy import deepcopy

import httpx
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow
from langflow.business.maintenance import status

from scripts.business.apply_compact_core import ROOT, SCHEME, local_context, login
from scripts.business.apply_core_classification import call, save

EVIDENCE = ROOT / "deploy/business/evidence/lookup-configuration-20261014"


def main():
    private, database, settings = local_context()
    try:
        if not status(database)["safe_to_upgrade"]:
            msg = "Pause intake and drain accepted tasks before updating the running canvas"
            raise ValueError(msg)
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            scheme = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == SCHEME)
            path = f"/api/v1/flows/{scheme['flow_id']}"
            original = call(http, "GET", path)
            backup = ROOT / "deploy/verification/.cache/lookup-configuration-20261014/canvas.json"
            if not backup.exists():
                save(backup, original)
            data = deepcopy(original["data"])
            before = from_langflow(data)
            for node in data["nodes"]:
                if not node["data"]["type"].split("@")[0].endswith("BusinessDatabaselookup"):
                    continue
                entry = node["data"]["node"]["template"]["configuration"]
                config = json.loads(entry["value"])
                # Existing source choices and identity prefixes have already been accepted.
                config["binding_source"] = {key: config.get(key, "") for key in ("connection", "schema", "table")}
                if config.get("source_identity"):
                    identity = config["source_identity"]
                    identity["name"] = identity.get("name") or "source"
                    identity["namespace"] = identity.get("namespace") or "lookup:" + node["id"]
                entry["value"] = json.dumps(config, ensure_ascii=False)
            graph = from_langflow(data)
            for old, new in zip(before["nodes"], graph["nodes"], strict=True):
                expected = deepcopy(new)
                expected["config"].pop("binding_source", None)
                prior = deepcopy(old)
                prior["config"].pop("binding_source", None)
                if expected != prior:
                    msg = "Refusing an unexpected change to existing business configuration"
                    raise ValueError(msg)
            package = inspect_graph(graph, database, settings, owner)
            save(EVIDENCE / "preflight.json", {"errors": package["errors"], "node_count": len(graph["nodes"])})
            call(http, "PATCH", path, json={"data": data})
            saved = from_langflow(call(http, "GET", path)["data"])
            if saved != graph:
                msg = "Canvas persistence did not preserve the reviewed graph"
                raise ValueError(msg)
            save(EVIDENCE / "graph.json", graph)
            save(EVIDENCE / "deployment.json", {
                "flow_id": scheme["flow_id"], "scheme": SCHEME,
                "node_count": len(graph["nodes"]), "activation": "pending_restart",
            })
            print("Saved the existing eleven-node canvas; business conditions and mappings unchanged.")
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
