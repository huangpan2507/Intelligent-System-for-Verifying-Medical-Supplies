# ruff: noqa: S101, PLR2004 - audit assertions protect the reviewed eleven-node canvas.
"""Install Q52-Q56 Results configuration and republish active packages after intake drains."""

import argparse
import copy
import json

import httpx
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow
from langflow.business.maintenance import status
from langflow.business.models import Release, Scheme, initialize
from langflow.verification.database import fingerprint
from sqlalchemy import func, select

from scripts.business.apply_compact_core import ROOT, SCHEME, local_context, login
from scripts.business.apply_core_classification import call, save

EVIDENCE = ROOT / "deploy/business/evidence/results-configuration-20261015"
BACKUP = ROOT / "deploy/verification/.cache/results-configuration-20261015"
RETIRED = {"key_fields", "reason_fields", "evidence_fields"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    private, database, settings = local_context()
    try:
        if args.apply and not status(database)["safe_to_upgrade"]:
            message = "Pause intake and drain tasks before migrating Results"
            raise ValueError(message)
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            owner = login(http, private)
            schemes = call(http, "GET", "/api/v1/business/schemes")
            core = next(s for s in schemes if s["code"] == SCHEME)
            path = f"/api/v1/flows/{core['flow_id']}"
            flow = call(http, "GET", path)
            canvas = copy.deepcopy(flow["data"])
            for node in canvas["nodes"]:
                if node["id"] == "Results":
                    field = node["data"]["node"]["template"]["configuration"]
                    previous = json.loads(field["value"])
                    field["value"] = json.dumps(
                        {"name": previous["name"], "result_template": "hip_knee_v1"}, ensure_ascii=False
                    )
            graph = from_langflow(canvas)
            assert len(graph["nodes"]) == 11
            assert next(n for n in graph["nodes"] if n["id"] == "Results")["config"]["result_template"] == "hip_knee_v1"
            assert canvas["edges"] == flow["data"]["edges"]
            plans = []
            for scheme in schemes:
                if not scheme["active_release_id"]:
                    continue
                with database.sessions() as session:
                    active = session.get(Release, scheme["active_release_id"])
                    proposal = copy.deepcopy(active.package["graph"])
                if scheme["code"] == SCHEME:
                    proposal = graph
                for node in proposal["nodes"]:
                    if node["kind"] == "output":
                        for key in RETIRED:
                            node["config"].pop(key, None)
                package = inspect_graph(proposal, database, settings, owner, strict=False)
                package["flow_id"] = active.package.get("flow_id", scheme["flow_id"])
                plans.append((scheme, package, active.content_hash))
            save(EVIDENCE / "migration-audit.json", [{"scheme": s["code"], "errors": p["errors"]} for s, p, _ in plans])
            assert not any(p["errors"] for _, p, _ in plans), [
                (s["code"], p["errors"]) for s, p, _ in plans if p["errors"]
            ]
            if not args.apply:
                print("Results migration validation passed; no canvas or release writes")
                return
            initialize(database)
            BACKUP.mkdir(parents=True, exist_ok=True)
            backup = BACKUP / f"{flow['id']}.json"
            if not backup.exists():
                save(backup, flow)
                backup.chmod(0o600)
            assert call(http, "GET", path)["data"] == flow["data"], "Canvas changed concurrently"
            if canvas != flow["data"]:
                call(http, "PATCH", path, json={"data": canvas})
            deployments = []
            for scheme, package, old_hash in plans:
                if fingerprint(package) == old_hash:
                    continue
                with database.sessions.begin() as session:
                    locked = session.scalar(select(Scheme).where(Scheme.code == scheme["code"]).with_for_update())
                    assert locked.active_release_id == scheme["active_release_id"]
                    assert locked.revision == scheme["revision"]
                    version = (
                        session.scalar(select(func.max(Release.version)).where(Release.scheme_code == scheme["code"]))
                        or 0
                    ) + 1
                    release = Release(
                        scheme_code=scheme["code"],
                        version=version,
                        package=package,
                        content_hash=fingerprint(package),
                        note="Q52-Q56: saved structured business results, evidence and Chinese narratives",
                    )
                    session.add(release)
                    session.flush()
                    locked.active_release_id = release.id
                    locked.revision += 1
                    if scheme["code"] == SCHEME:
                        locked.draft = package["graph"]
                    deployment = {
                        "scheme": scheme["code"],
                        "flow_id": scheme["flow_id"],
                        "release_id": release.id,
                        "version": version,
                        "node_count": len(package["graph"]["nodes"]),
                    }
                    deployments.append(deployment)
                    if scheme["code"] == SCHEME:
                        save(EVIDENCE / "deployment.json", deployment)
            save(EVIDENCE / "deployments.json", deployments)
            print(json.dumps(deployments, ensure_ascii=False))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
