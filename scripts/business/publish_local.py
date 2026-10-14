"""Validate active local schemes against the current code before restarting the Worker."""

import json

import httpx
from langflow.business.compiler import runtime_digest
from langflow.business.maintenance import status

from scripts.business.apply_compact_core import SCHEME, local_context, login
from scripts.business.apply_core_classification import call


def main():
    private, database, _ = local_context()
    try:
        if not status(database)["safe_to_upgrade"]:
            msg = "Pause intake and drain accepted tasks before publishing"
            raise ValueError(msg)
        published = []
        with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
            login(http, private)
            for scheme in call(http, "GET", "/api/v1/business/schemes"):
                if not scheme["active_release_id"]:
                    continue
                code = scheme["code"]
                releases = call(http, "GET", f"/api/v1/business/schemes/{code}/releases")
                active = next(r for r in releases if r["id"] == scheme["active_release_id"])
                if active["package"]["runtime_digest"] == runtime_digest():
                    continue
                # Publish the core canvas. For other schemes retain their selected configuration,
                # without substituting an unreviewed draft. All must pass the current contract.
                suffix = "" if code == SCHEME else f"/from/{active['id']}"
                release = call(
                    http,
                    "POST",
                    f"/api/v1/business/schemes/{code}/releases{suffix}",
                    json={"expected_revision": scheme["revision"], "note": "Validated against current capabilities"},
                )
                current = next(s for s in call(http, "GET", "/api/v1/business/schemes") if s["code"] == code)
                call(
                    http,
                    "PUT",
                    f"/api/v1/business/schemes/{code}/active",
                    json={"expected_revision": current["revision"], "release_id": release["id"]},
                )
                published.append({"scheme": code, "release_id": release["id"], "version": release["version"]})
        print(json.dumps({"releases": published}), flush=True)
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
