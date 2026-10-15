# ruff: noqa: S101, PLR2004, RUF001 - local migration checks and reviewable deployment reports.
"""Audit/remove Business Compare tolerance from current canvases and active schemes (Q50-Q51)."""

import argparse
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

EVIDENCE = ROOT / "deploy/business/evidence/compare-configuration-20261015"
BACKUP = ROOT / "deploy/verification/.cache/compare-configuration-20261015"


def clean_config(config, node_id):
    removed = []
    for index, item in enumerate(config.get("comparisons", [])):
        if "tolerance" in item:
            removed.append({"node": node_id, "comparison": index, "previous_tolerance": item.pop("tolerance")})
    return removed


def clean_canvas(canvas):
    removed = []
    for node in canvas.get("nodes", []):
        kind = node.get("data", {}).get("type", "").split(":")[-1].split("@")[0]
        if kind == "VerificationResultComparison":
            template = node["data"]["node"]["template"]
            removed.extend(
                {"node": node["id"], "field": key, "previous_tolerance": template.pop(key).get("value")}
                for key in ("quantity_tolerance", "money_tolerance")
                if key in template
            )
            description = node["data"]["node"].get("description", "")
            node["data"]["node"]["description"] = description.replace(
                "选择比较项目和绝对差容差。", "选择比较项目，数值严格相等，不设置容差。"
            )
            continue
        if kind != "BusinessCompare":
            continue
        field = node["data"]["node"]["template"]["configuration"]
        config = json.loads(field["value"])
        changes = clean_config(config, node["id"])
        if changes:
            field["value"] = json.dumps(config, ensure_ascii=False)
            removed.extend(changes)
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    private, database, settings = local_context()
    try:
        if args.apply and not status(database)["safe_to_upgrade"]:
            message = "Pause intake and drain tasks before migrating Compare"
            raise ValueError(message)
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            flows = call(http, "GET", "/api/v1/flows/", params={"get_all": "true"})
            drafts, audit = {}, {"canvases_checked": len(flows), "canvases": [], "active_schemes": []}
            for flow in flows:
                canvas = copy.deepcopy(flow.get("data") or {})
                removed = clean_canvas(canvas)
                drafts[flow["id"]] = (flow, canvas)
                if removed:
                    audit["canvases"].append({"flow_id": flow["id"], "removed": removed})
            schemes = call(http, "GET", "/api/v1/business/schemes")
            plans = []
            # Validate all proposed active packages before changing any canvas.
            for scheme in schemes:
                if not scheme["active_release_id"]:
                    continue
                with database.sessions() as session:
                    previous = session.get(Release, scheme["active_release_id"])
                    graph = copy.deepcopy(previous.package["graph"])
                removed = []
                for node in graph["nodes"]:
                    if node["kind"] == "compare":
                        removed.extend(clean_config(node["config"], node["id"]))
                if scheme["code"] == SCHEME:
                    graph = from_langflow(drafts[scheme["flow_id"]][1])
                    assert len(graph["nodes"]) == 11
                package = inspect_graph(graph, database, settings, owner, strict=False)
                audit["active_schemes"].append(
                    {"scheme": scheme["code"], "removed": removed, "errors": package["errors"]}
                )
                package["flow_id"] = previous.package.get("flow_id", scheme["flow_id"])
                if fingerprint(package) != previous.content_hash:
                    plans.append((scheme, package))
            save(EVIDENCE / "migration-audit.json", audit)
            assert not any(p["errors"] for p in audit["active_schemes"]), audit["active_schemes"]
            if not args.apply:
                print(json.dumps(audit, ensure_ascii=False))
                return
            for flow, canvas in drafts.values():
                if canvas == flow.get("data"):
                    continue
                path = f"/api/v1/flows/{flow['id']}"
                backup = BACKUP / f"{flow['id']}.json"
                if not backup.exists():
                    save(backup, flow)
                    backup.chmod(0o600)
                assert call(http, "GET", path)["data"] == flow["data"], "Canvas changed concurrently"
                assert canvas["edges"] == flow["data"]["edges"]
                call(http, "PATCH", path, json={"data": canvas})
                assert call(http, "GET", path)["data"] == canvas
            deployed = []
            for scheme, package in plans:
                current = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == scheme["code"])
                assert current["active_release_id"] == scheme["active_release_id"], (
                    "Active version changed concurrently"
                )
                with database.sessions.begin() as session:
                    locked = session.scalar(select(Scheme).where(Scheme.code == scheme["code"]).with_for_update())
                    assert locked.revision == current["revision"]
                    version = (
                        session.scalar(select(func.max(Release.version)).where(Release.scheme_code == scheme["code"]))
                        or 0
                    ) + 1
                    release = Release(
                        scheme_code=scheme["code"],
                        version=version,
                        package=package,
                        content_hash=fingerprint(package),
                        note="Q50-Q51: strict equality without tolerance; calculate before comparing",
                    )
                    session.add(release)
                    session.flush()
                    release_id = release.id
                call(
                    http,
                    "PUT",
                    f"/api/v1/business/schemes/{scheme['code']}/active",
                    json={"expected_revision": current["revision"], "release_id": release_id},
                )
                result = {
                    "scheme": scheme["code"],
                    "flow_id": scheme["flow_id"],
                    "release_id": release_id,
                    "version": version,
                    "node_count": len(package["graph"]["nodes"]),
                }
                deployed.append(result)
                if scheme["code"] == SCHEME:
                    save(EVIDENCE / "deployment.json", result)
            save(EVIDENCE / "deployments.json", deployed)
            print(json.dumps(deployed, ensure_ascii=False))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
