# ruff: noqa: S101, PLR2004 - live assertions against two synthetic core fixtures.
"""Verify a real Worker task on the compact canvas; --task rechecks without another model call."""

import argparse
import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

from scripts.business.apply_compact_core import ROOT, SCHEME
from scripts.business.apply_core_classification import call, save
from scripts.business.apply_study_relevance import EVIDENCE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task")
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    evidence = args.evidence_dir
    private = dotenv_values(ROOT / "deploy/verification/.env")
    token = json.loads(private["VERIFICATION_CLIENTS"])["demo-regulator"]
    port = int(private.get("VERIFICATION_SOURCE_API_PORT") or 8081)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, timeout=60
    ) as http:
        task = (
            call(http, "GET", f"/api/v1/business/tasks/{args.task}")
            if args.task
            else call(
                http,
                "POST",
                "/api/v1/business/tasks",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "scheme": SCHEME,
                    "external_task_id": "MOCK-COMPACT-" + str(uuid4()),
                    "parameters": {
                        "hospital_name": "核心流程模拟医院",
                        "start": "2025-08-01 00:00:00",
                        "end": "2025-08-31 23:59:59",
                    },
                },
            )
        )
        print(json.dumps({"task_id": task["id"], "status": task["status"]}), flush=True)
        path = f"/api/v1/business/tasks/{task['id']}"
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            task = call(http, "GET", path)
            if task["status"] not in {"waiting", "running"}:
                break
            time.sleep(2)
        save(evidence / "task.json", task)
        assert task["status"] == "completed", task.get("error") or task["progress"]

        def dataset(node, output="data"):
            # Some internal receipts share a node label; public progress identifies its final output.
            ref = task["progress"][node]["outputs"][output]
            return call(http, "GET", path + "/datasets/" + ref["id"])

        results = dataset("Results")
        rows = results["rows"]
        assert results["total"] == 2
        assert {r["classification_method"] for r in rows} == {"rule", "model"}
        assert {r["target_category"] for r in rows} == {"人工髋关节", "人工膝关节"}
        assert all(r["category_status"] == r["quantity_status"] == r["amount_status"] == "equal" for r in rows)
        assert {r["SETL_FEE_LIST_ID"]: len(json.loads(r["image_manifest"])) for r in rows} == {
            "MOCK-DETAIL-HIP": 7,
            "MOCK-DETAIL-KNEE": 5,
        }
        images = dataset("Images")
        image_rows = {r["SETL_FEE_LIST_ID"]: r for r in images["rows"]}
        for row in rows:
            contexts = json.loads(image_rows[row["SETL_FEE_LIST_ID"]]["image_manifest_context"])
            assert all(r["RPT_NO"] == row["RPT_NO"] for r in contexts)
            assert {r["address"] for r in contexts} == set(json.loads(row["image_manifest"]))
            assert {r["series_modality"] for r in contexts} == {"DR", "CT"}
            assert all(r["study_relevance_code_source"] and r["study_relevance"] == "候选相关" for r in contexts)
        assert any(str(r["OP_EM_MARK"]) == "1" and r["target_category"] == "人工膝关节" for r in rows)
        assert set(task["progress"]["Classification"]["outputs"]) == {"data", "issues"}
        assert task["classification_counts"] == {"continue": 7, "excluded": 0, "uncompared": 0}
        assert task["unresolved_rows"] == 0
        assert len(task["progress"]) == 11
        assert task["assessment"]["state"] == "accounted"
        assert task["assessment"]["coverage_gap_records"] == 0
        counts = {
            name: dataset(name, output)["total"]
            for name, output in [
                ("Settlements", "data"),
                ("SettlementChecks", "valid"),
                ("Classification", "data"),
                ("Studies", "data"),
                ("StudyRelevance", "data"),
                ("Series", "data"),
                ("Images", "data"),
                ("Observation", "data"),
                ("Compare", "data"),
                ("Results", "data"),
            ]
        }
        assert all(
            count == (5 if node in {"Studies", "StudyRelevance", "Series"} else 2) for node, count in counts.items()
        )
        relevance = dataset("StudyRelevance")
        assert sum(r["study_relevance_method"] == "rule" for r in relevance["rows"]) == 4
        assert sum(r["study_relevance_method"] == "model" for r in relevance["rows"]) == 1
        assert {(r["target_category"], r["study_chk_modality"]) for r in relevance["rows"]} == {
            (joint, modality) for joint in ["人工髋关节", "人工膝关节"] for modality in ["DR", "CT"]
        }
        assert set(task["progress"]["StudyRelevance"]["outputs"]) == {"data", "issues"}
        save(evidence / "study-relevance-rows.json", relevance)
        requests = call(http, "GET", path + "/requests")["items"]
        assert len([r for r in requests if r["node_id"] == "Classification"]) == 1
        assert len([r for r in requests if r["node_id"] == "StudyRelevance"]) == 1
        assert len([r for r in requests if r["node_id"] == "Observation"]) == 2
        observation_receipts = []
        for receipt in requests:
            if receipt["node_id"] != "Observation":
                continue
            detail = call(http, "GET", path + "/requests/" + receipt["id"])
            context = json.loads(detail["payload"]["evidence_context"])
            assert context
            assert all(item.get("RPT_NO") for item in context)
            assert detail["transport"] == "responded"
            assert detail["remote"] == "completed"
            matching = [
                r for r in images["rows"] if r["image_manifest_context"] == detail["payload"]["evidence_context"]
            ]
            assert len(matching) == 1
            assert all(item["RPT_NO"] == matching[0]["RPT_NO"] for item in context)
            observation_receipts.append(detail)
        save(evidence / "observation-requests.json", observation_receipts)
        expected = {
            "MOCK-DETAIL-HIP": ("人工髋关节", 10000),
            "MOCK-DETAIL-KNEE": ("人工膝关节", 5000),
        }
        assert {row["SETL_FEE_LIST_ID"] for row in rows} == set(expected)
        for row in rows:
            category, price = expected[row["SETL_FEE_LIST_ID"]]
            assert row["target_category"] == row["recognized_category"] == category
            assert all(Decimal(str(row[key])) == 1 for key in ["CNT", "recognized_quantity"])
            assert all(Decimal(str(row[key])) == price for key in ["PRIC", "settled_amount", "observed_amount"])
        save(evidence / "result-rows.json", results)
        save(evidence / "image-manifest-rows.json", images)
        saved_results = call(http, "GET", path + "/results?node_id=Results")
        assert saved_results["total"] == 2
        saved_evidence = {}
        for result in saved_results["items"]:
            assert result["status"] == "normal"
            assert result["complete"]
            assert "三项比较一致" in result["narrative"]
            assert "模拟影像识别" in result["narrative"]
            assert result["release_id"] == task["release_id"]
            assert result["facts"]["RPT_NO"] in result["narrative"]
            links = call(http, "GET", path + f"/results/{result['id']}/evidence?limit=200")
            assert links["total"] == len(links["items"])
            assert {item["kind"] for item in links["items"]} == {"source", "recognition", "image"}
            images_saved = [item["context"] for item in links["items"] if item["kind"] == "image"]
            assert all(item["RPT_NO"] == result["facts"]["RPT_NO"] for item in images_saved)
            assert {item["address"] for item in images_saved} == set(json.loads(result["facts"]["image_manifest"]))
            assert all(item["study_ris_study_id"] and item["series_id"] for item in images_saved)
            assert any(item["request_id"] == result["facts"]["_request_id"] for item in links["items"])
            saved_evidence[result["id"]] = links
        save(evidence / "saved-results.json", saved_results)
        save(evidence / "saved-result-evidence.json", saved_evidence)
        report = {
            "scheme": SCHEME,
            "task_id": task["id"],
            "release_id": task["release_id"],
            "status": task["status"],
            "node_count": 11,
            "counts": counts,
            "assessment": task["assessment"],
            "matches_expected_samples": True,
            "saved_business_results": saved_results["total"],
            "saved_evidence_links": sum(links["total"] for links in saved_evidence.values()),
            "real_text_model_calls": 2,
            "image_observation_simulated": True,
            "cross_business_acceptance": "deferred_by_Q24",
        }
        save(evidence / "acceptance.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
