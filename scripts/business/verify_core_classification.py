# ruff: noqa: S101, PLR2004 - live acceptance assertions against the two agreed fixtures.
"""Submit one synthetic regulatory task and verify the complete live Worker chain."""

import argparse
import json
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values

from scripts.business.apply_core_classification import EVIDENCE, FLOW, ROOT, SCHEME, call, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="Inspect an existing task without another paid model call")
    args = parser.parse_args()
    private = dotenv_values(ROOT / "deploy/verification/.env")
    token = next(iter(json.loads(private["VERIFICATION_CLIENTS"]).values()))
    port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, timeout=60
    ) as http:
        body = {
            "scheme": SCHEME,
            "external_task_id": "MOCK-REG-CLASSIFICATION-" + str(uuid4()),
            "parameters": {
                "hospital_name": "核心流程模拟医院",
                "start": "2025-08-01 00:00:00",
                "end": "2025-08-31 23:59:59",
            },
        }
        task = (
            call(http, "GET", f"/api/v1/business/tasks/{args.task}")
            if args.task
            else call(http, "POST", "/api/v1/business/tasks", json=body, headers={"Idempotency-Key": str(uuid4())})
        )
        path = f"/api/v1/business/tasks/{task['id']}"
        print(json.dumps({"task_id": task["id"], "status": task["status"]}), flush=True)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            task = call(http, "GET", path)
            if task["status"] not in {"waiting", "running"}:
                break
            time.sleep(2)
        save(EVIDENCE / "task.json", task)
        assert task["status"] == "completed", task.get("error") or task["assessment"]
        graph = json.loads((EVIDENCE / "graph.json").read_text())
        ids = {n["label"]: n["id"] for n in graph["nodes"]}

        def dataset(name, port="data"):
            item = next(d for d in task["datasets"] if d["node_id"] == ids[name] and d["port"] == port)
            return call(http, "GET", path + "/datasets/" + item["id"])

        results = dataset("Results")
        classifications = dataset("ClassificationResults")
        save(EVIDENCE / "result-rows.json", results)
        save(EVIDENCE / "classification-rows.json", classifications)
        rows = results["rows"]
        assert results["total"] == 2
        assert {r["classification_method"] for r in rows} == {"rule", "model"}
        assert {r["target_category"] for r in rows} == {"人工髋关节", "人工膝关节"}
        assert all(r["category_status"] == r["quantity_status"] == r["amount_status"] == "equal" for r in rows)
        assert any(str(r["OP_EM_MARK"]) == "1" and r["target_category"] == "人工膝关节" for r in rows)
        counts = {
            name: dataset(name, port)["total"]
            for name, port in [
                ("Settlements", "data"),
                ("Studies", "data"),
                ("Series", "data"),
                ("NameModel", "data"),
                ("Images", "data"),
                ("Manifests", "data"),
                ("Observation", "data"),
            ]
        }
        assert counts == {
            "Settlements": 2,
            "Studies": 2,
            "Series": 2,
            "NameModel": 1,
            "Images": 4,
            "Manifests": 2,
            "Observation": 2,
        }
        requests = call(http, "GET", path + "/requests")["items"]
        save(
            EVIDENCE / "request-summary.json",
            [{k: r.get(k) for k in ["id", "node_id", "connection_id", "transport", "validity"]} for r in requests],
        )
        # Model/observation calls use the request ledger; read APIs record page counts on raw datasets.
        assert {r["node_id"] for r in requests} == {ids["NameModel"], ids["Observation"]}
        assert len(requests) == 3
        image_read = next(d for d in task["datasets"] if d["node_id"] == ids["Images"] and d["raw"])
        assert image_read["provenance"]["pagination"]["count"] == 2
        model_request = next(r for r in requests if r["node_id"] == ids["NameModel"])
        save(EVIDENCE / "task-model-response.json", model_request["response"])
        assert task["assessment"]["state"] == "accounted"
        assert task["assessment"]["coverage_gap_records"] == 0
        report = {
            "flow_id": FLOW,
            "task_id": task["id"],
            "release_id": task["release_id"],
            "status": task["status"],
            "counts": counts,
            "assessment": task["assessment"],
            "source_scope": "query_returned_settlement_rows",
            "real_text_model_calls": 1,
            "inspection_and_series_via_database": True,
            "outpatient_included": True,
            "image_observation_simulated": True,
            "all_six_comparisons_equal": True,
        }
        save(EVIDENCE / "acceptance.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
