"""Refresh known three-port Validate canvases, preserving existing consumers and layout."""

import argparse
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values
from langflow.business.validate_migration import migrate_canvas

ROOT = Path(__file__).resolve().parents[2]


def call(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow-id", help="Limit migration to one owned flow; otherwise inspect all owned flows")
    args = parser.parse_args()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    backup_root = ROOT / "deploy/verification/.cache/validate-output-migration"
    backup_root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
        login = call(
            http,
            "POST",
            "/api/v1/login",
            data={
                "username": "verification-admin",
                "password": private["LANGFLOW_SUPERUSER_PASSWORD"],
            },
        )
        http.headers["Authorization"] = "Bearer " + login["access_token"]
        flows = (
            [call(http, "GET", f"/api/v1/flows/{args.flow_id}")]
            if args.flow_id
            else call(http, "GET", "/api/v1/flows/", params={"get_all": "true"})
        )
        changed = []
        for flow in flows:
            original = flow.get("data") or {}
            canvas = migrate_canvas(original)
            if canvas == original:
                continue
            path = f"/api/v1/flows/{flow['id']}"
            backup = backup_root / f"{flow['id']}.json"
            if not backup.exists():
                backup.write_text(json.dumps(flow, ensure_ascii=False, indent=2) + "\n")
                backup.chmod(0o600)
            if call(http, "GET", path)["data"] != original:
                msg = f"Canvas {flow['id']} changed concurrently; reload before migration"
                raise RuntimeError(msg)
            call(http, "PATCH", path, json={"data": canvas})
            if call(http, "GET", path)["data"] != canvas:
                msg = f"Canvas {flow['id']} did not retain its migrated configuration"
                raise RuntimeError(msg)
            changed.append(
                {"id": flow["id"], "name": flow["name"], "added_filters": len(canvas["nodes"]) - len(original["nodes"])}
            )
        report = {"checked": len(flows), "changed": changed}
        if changed:
            (backup_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
