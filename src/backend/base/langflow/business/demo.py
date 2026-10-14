"""Explicit synthetic source contracts for the consumable example template."""

import json
from copy import deepcopy
from datetime import datetime

from fastapi import Depends, HTTPException


def register_demo(app, authenticate):
    from langflow.verification.demo import settlement_fixture

    @app.post("/business/settlements", dependencies=[Depends(authenticate)])
    def settlements(body: dict):
        rows = [settlement_fixture("hip"), settlement_fixture("knee")]
        for code, label in [
            ("DEMO-SHOULDER", "other-joint"),
            ("DEMO-SYRINGE", "other-consumable"),
            ("DEMO-UNKNOWN", "unclassified"),
        ]:
            row = deepcopy(rows[0])
            row.update(detail_id=label, patient_id=label, catalog_code=code, item_name=label, quantity="1")
            rows.append(row)
        missing = deepcopy(rows[1])
        missing.update(detail_id="missing-payment", insurance_paid=None)
        rows.append(missing)
        if body.get("scenario") == "adversarial":
            for case in [
                "negative",
                "uncertain",
                "category-different",
                "no-images",
                "mixed-price",
                "missing-identity",
                "conflict",
                "scope-failure",
            ]:
                row = deepcopy(rows[1])
                row.update(detail_id=case, patient_id="case-" + case, encounter_id="visit-" + case)
                rows.append(row)
                if case == "mixed-price":
                    extra = deepcopy(row)
                    extra.update(detail_id=case + "-extra", unit_price="6000.00", amount="6000.00")
                    rows.append(extra)
                if case == "missing-identity":
                    row["detail_id"] = None
                if case == "conflict":
                    extra = deepcopy(row)
                    extra["quantity"] = "2"
                    rows.append(extra)
            rows.append(deepcopy(rows[0]))
            outside = deepcopy(rows[1])
            outside.update(
                detail_id="examination", patient_id="outside-examination", medical_consumable=False, quantity=None
            )
            rows.append(outside)
        for row in rows:
            row["billed_amount"] = row["amount"]
        start = datetime.fromisoformat(body["start"]).date()
        end = datetime.fromisoformat(body["end"]).date()
        if start >= end:
            raise HTTPException(422, "Start must precede end")
        rows = [
            r
            for r in rows
            if r["hospital_id"] == body["hospital"]
            and start <= datetime.fromisoformat(r["settlement_time"]).date() < end
        ]
        return {"items": rows, "complete": True, "simulated": True}

    @app.get("/business/catalog", dependencies=[Depends(authenticate)])
    def catalog():
        return {
            "items": [
                {"code": code, "category": category}
                for code, category in [
                    ("DEMO-HIP", "hip_prosthesis"),
                    ("DEMO-KNEE", "knee_prosthesis"),
                    ("DEMO-SHOULDER", "shoulder_prosthesis"),
                    ("DEMO-SYRINGE", "other_consumable"),
                ]
            ],
            "version": "synthetic-catalog-v1",
            "simulated": True,
            "complete": True,
        }

    @app.get("/business/studies", dependencies=[Depends(authenticate)])
    def studies(system_patient_id: str, organ_code: str, op_em_hp_ex_no: str):
        if system_patient_id == "case-scope-failure":
            raise HTTPException(503, "Synthetic independent scope failure")
        rows = (
            []
            if system_patient_id == "case-no-images"
            else [
                {
                    "study_primary_id": "study:" + system_patient_id,
                    "patient_id": system_patient_id,
                    "hospital_id": organ_code,
                    "encounter_id": op_em_hp_ex_no,
                    "scope_confirmed": True,
                }
            ]
        )
        return {"items": rows, "complete": True, "simulated": True}

    @app.get("/business/series", dependencies=[Depends(authenticate)])
    def series(study_primary_id: str):
        return {"items": [{"series_id": "series:" + study_primary_id}], "complete": True, "simulated": True}

    @app.get("/business/images", dependencies=[Depends(authenticate)])
    def images(series_id: str):
        return {
            "items": [{"sop_instance_uid": "image:" + series_id, "file_ref": "synthetic://" + series_id}],
            "complete": True,
            "simulated": True,
        }

    @app.post("/business/imaging", dependencies=[Depends(authenticate)])
    def imaging(body: dict):
        # Observation fixtures are independent of submitted target category and expected quantity.
        patient = body.get("patient", "")
        joint = "hip" if patient == "synthetic-patient-hip" else "knee"
        category = "hip_prosthesis" if patient == "case-category-different" else joint + "_prosthesis"
        manifest = json.loads(body.get("evidence") or "[]")
        matched = bool(manifest) and body.get("hospital") == "synthetic-hospital"
        return {
            "recognized_category": category if matched else None,
            "recognized_quantity": ("-1" if patient == "case-negative" else "1") if matched else None,
            "observed_unit": "set" if matched else None,
            "coverage_confirmed": matched and patient != "case-uncertain",
            "recognition_confirmed": matched,
            "evidence_ref": f"synthetic-review:{joint}:v1" if matched else None,
            "simulated": True,
            "study_id": f"study-{joint}" if matched else None,
            "note": "Synthetic checked scope and recognition; not a real medical model",
        }
