# ruff: noqa: S101, PLR2004 - explicitly requested local canvas update and assertions.
"""Apply Q47-Q49 to the latest core canvas without replacing unrelated nodes."""

import copy
import json

import httpx
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow
from langflow.business.maintenance import status
from langflow.business.models import Release, Scheme
from langflow.verification.database import fingerprint
from sqlalchemy import func, select

from scripts.business.apply_compact_core import ROOT, SCHEME, local_context, login
from scripts.business.apply_core_classification import call, save

EVIDENCE = ROOT / "deploy/business/evidence/observation-configuration-20261015"


def configure(canvas):
    for node in canvas["nodes"]:
        if node["id"] not in {"Observation", "Compare", "Results"}:
            continue
        field = node["data"]["node"]["template"]["configuration"]
        config = json.loads(field["value"])
        if node["id"] == "Observation":
            for key in ("quantity_field", "unit_field", "unit_value"):
                config.pop(key, None)
            checks = config.get("result_checks", {})
            checks["conditions"] = [c for c in checks.get("conditions", []) if c["field"] != "observed_unit"]
        elif node["id"] == "Compare":
            config["calculations"] = [c for c in config["calculations"] if c["output"] != "unit"]
        else:
            config["columns"] = [name for name in config["columns"] if name != "unit"]
        field["value"] = json.dumps(config, ensure_ascii=False)


def main():
    private, database, settings = local_context()
    try:
        if not status(database)["safe_to_upgrade"]:
            message = "Pause intake and drain accepted tasks before updating the canvas"
            raise ValueError(message)
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            scheme = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == SCHEME)
            path = f"/api/v1/flows/{scheme['flow_id']}"
            original = call(http, "GET", path)
            backup = ROOT / "deploy/verification/.cache/observation-configuration-20261015/canvas.json"
            if not backup.exists():
                save(backup, original)
            canvas = copy.deepcopy(original["data"])
            configure(canvas)
            graph = from_langflow(canvas)
            inspection = inspect_graph(graph, database, settings, owner, strict=False)
            save(EVIDENCE / "preflight.json", {"errors": inspection["errors"], "node_count": len(graph["nodes"])})
            assert not inspection["errors"], inspection["errors"]
            assert len(graph["nodes"]) == 11
            assert canvas["edges"] == original["data"]["edges"]
            assert call(http, "GET", path)["data"] == original["data"], "Canvas changed during preparation"
            call(http, "PATCH", path, json={"data": canvas})
            assert call(http, "GET", path)["data"] == canvas
            release = call(
                http,
                "POST",
                f"/api/v1/business/schemes/{SCHEME}/releases",
                json={
                    "expected_revision": scheme["revision"],
                    "note": "Observation: grouped configuration and numeric comparison without unit gating (Q47-Q49)",
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
            }
            save(EVIDENCE / "deployment.json", report)
            print(json.dumps(report))
            # Other active examples must also shed the removed input fields before
            # the project start script validates their selected releases. Preserve
            # their checks and any unpublished draft rather than replacing it.
            migrated = []
            for other in call(http, "GET", "/api/v1/business/schemes"):
                if other["code"] == SCHEME or not other["active_release_id"]:
                    continue
                with database.sessions() as session:
                    previous = session.get(Release, other["active_release_id"])
                    graph = copy.deepcopy(previous.package["graph"])
                removed = []
                for node in graph["nodes"]:
                    if node["kind"] != "imaging":
                        continue
                    for key in ("unit_field", "unit_value"):
                        if key in node["config"]:
                            node["config"].pop(key)
                            removed.append({"node": node["id"], "field": key})
                if not removed:
                    continue
                package = inspect_graph(graph, database, settings, owner)
                package["flow_id"] = previous.package.get("flow_id", other["flow_id"])
                other_path = f"/api/v1/flows/{other['flow_id']}"
                expected_revision = other["revision"]
                draft = call(http, "GET", other_path)
                updated_canvas = copy.deepcopy(draft["data"])
                for node in updated_canvas["nodes"]:
                    if "BusinessImaging" not in node["data"].get("type", ""):
                        continue
                    field = node["data"]["node"]["template"]["configuration"]
                    config = json.loads(field["value"])
                    if not any(key in config for key in ("unit_field", "unit_value")):
                        continue
                    config.pop("unit_field", None)
                    config.pop("unit_value", None)
                    field["value"] = json.dumps(config, ensure_ascii=False)
                if updated_canvas != draft["data"]:
                    save(backup.parent / f"{other['flow_id']}.json", draft)
                    assert call(http, "GET", other_path)["data"] == draft["data"], "Draft changed during cleanup"
                    call(http, "PATCH", other_path, json={"data": updated_canvas})
                    expected_revision = next(
                        s["revision"]
                        for s in call(http, "GET", "/api/v1/business/schemes")
                        if s["code"] == other["code"]
                    )
                with database.sessions.begin() as session:
                    current = session.scalar(select(Scheme).where(Scheme.code == other["code"]).with_for_update())
                    assert current.revision == expected_revision, "Scheme changed during preparation"
                    version = (
                        session.scalar(select(func.max(Release.version)).where(Release.scheme_code == other["code"]))
                        or 0
                    ) + 1
                    updated = Release(
                        scheme_code=other["code"],
                        version=version,
                        package=package,
                        content_hash=fingerprint(package),
                        note="Remove discontinued imaging unit inputs; retain existing checks",
                    )
                    session.add(updated)
                    session.flush()
                    updated_id = updated.id
                call(
                    http,
                    "PUT",
                    f"/api/v1/business/schemes/{other['code']}/active",
                    json={
                        "expected_revision": expected_revision,
                        "release_id": updated_id,
                    },
                )
                migrated.append(
                    {
                        "scheme": other["code"],
                        "previous": other["active_release_id"],
                        "release_id": updated_id,
                        "removed": removed,
                    }
                )
            save(EVIDENCE / "retired-input-cleanup.json", migrated)
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
