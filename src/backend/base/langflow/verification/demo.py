"""Synthetic contract service. This contains no DICOM downloader or trained model."""

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException

from langflow.verification.api import Credentials  # noqa: TC001 - FastAPI resolves this dependency at runtime.
from langflow.verification.schemas import SettlementQuery  # noqa: TC001 - FastAPI runtime annotation.
from langflow.verification.settings import MIN_TOKEN_LENGTH, FlowSettings


def example_task() -> dict:
    return {
        "hospital_scope": "常州市第一人民医院",
        "settlement_time_range": {
            "start_inclusive": "2024-06-01T00:00:00+08:00",
            "end_exclusive": "2025-09-01T00:00:00+08:00",
        },
        "rule": "高值耗材智能体",
    }


def seed_demo(database) -> None:
    from langflow.verification.database import HospitalScope, ReviewDetail, ReviewRecord

    with database.sessions.begin() as session:
        if session.get(HospitalScope, "demo-changzhou") is None:
            session.add(
                HospitalScope(
                    id="demo-changzhou",
                    name="常州市第一人民医院",
                    aliases=["demo-changzhou"],
                    members=[{"settlement_id": "synthetic-hospital", "organ_code": "synthetic-hospital"}],
                    allowed_sources=["demo-regulator"],
                )
            )
        for joint in ["hip", "knee"]:
            if session.get(ReviewRecord, joint):
                continue
            ids = ["detail-hip", "detail-hip-extra"] if joint == "hip" else ["detail-knee"]
            record = ReviewRecord(
                id=joint,
                simulated=True,
                payload={
                    "scope_id": joint,
                    "detail_ids": ids,
                    "study_ids": [f"study-{joint}"],
                    "category": f"{joint}_prosthesis",
                    "unit": "set",
                    "target_confirmed": True,
                    "coverage_confirmed": True,
                    "counting_validated": True,
                    "evidence_ref": f"synthetic-review:{joint}:v1",
                },
            )
            session.add(record)
            session.flush()
            session.add_all([ReviewDetail(detail_id=key, review_id=joint) for key in ids])


def settlement_fixture(joint: str) -> dict:
    hip = joint == "hip"
    return {
        "detail_id": f"detail-{joint}",
        "patient_id": f"synthetic-patient-{joint}",
        "hospital_id": "synthetic-hospital",
        "encounter_id": f"synthetic-visit-{joint}",
        "encounter_type": "inpatient",
        "catalog_code": "DEMO-HIP" if hip else "DEMO-KNEE",
        "item_name": "人工髋关节(模拟)" if hip else "人工膝关节(模拟)",
        "medical_consumable": True,
        "insurance_paid": True,
        "quantity": "2" if hip else "1",
        "unit": "set",
        "unit_price": "10000.00" if hip else "5000.00",
        "amount": "20000.00" if hip else "5000.00",
        "settlement_time": "2025-08-20T10:00:00+08:00",
        "update_time": "2025-08-21T10:00:00+08:00",
        "is_reversal": False,
        "raw": {"simulated": True},
    }


def study_fixture(joint: str) -> dict:
    return {
        "study_id": f"study-{joint}",
        "patient_id": f"synthetic-patient-{joint}",
        "hospital_id": "synthetic-hospital",
        "encounter_id": f"synthetic-visit-{joint}",
        "encounter_type": "inpatient",
        "modality": "DR",
        "checked_at": "2025-08-19T10:00:00+08:00",
        "project_name": f"Synthetic {joint} radiograph",
        "body_part": joint,
    }


def create_demo_app(settings: FlowSettings | None = None) -> FastAPI:
    settings = settings or FlowSettings()
    if not settings.demo_mode:
        msg = "Synthetic services require VERIFICATION_DEMO_MODE=true"
        raise ValueError(msg)
    if len(settings.upstream_token.get_secret_value()) < MIN_TOKEN_LENGTH:
        msg = "Configure a demo upstream token with at least 16 characters"
        raise ValueError(msg)

    def authenticate(credentials: Credentials) -> None:
        if not secrets.compare_digest(credentials.credentials, settings.upstream_token.get_secret_value()):
            raise HTTPException(401, "Invalid demo service credential")

    def authenticate_imaging(x_token: str = Header(alias="X-Token")) -> None:
        token = settings.imaging_token.get_secret_value() or settings.upstream_token.get_secret_value()
        if not secrets.compare_digest(x_token, token):
            raise HTTPException(401, "Invalid demo image cloud credential")

    app = FastAPI(title="SYNTHETIC verification upstreams")

    @app.post("/v1/settlements/query", dependencies=[Depends(authenticate)])
    def settlements(body: SettlementQuery) -> dict:
        from langflow.verification.database import fingerprint

        rows = [settlement_fixture(joint) for joint in ("hip", "knee")]
        rows[0]["quantity"], rows[0]["amount"] = "1", "10000.00"
        rows.append({**rows[0], "detail_id": "detail-hip-extra"})
        # Same unit deliberately spans pages; the adapter must group across page boundaries.
        rows.sort(key=lambda row: row["detail_id"])
        token = fingerprint({"rows": rows})
        if body.snapshot_token and body.snapshot_token != token:
            raise HTTPException(409, "Synthetic source snapshot changed")
        filtered = [
            r
            for r in rows
            if r["hospital_id"] in body.hospital_ids
            and body.settlement_time_range.start_inclusive
            <= datetime.fromisoformat(r["settlement_time"])
            < body.settlement_time_range.end_exclusive
        ]
        offset = int(body.cursor or "0")
        items = filtered[offset : offset + body.limit]
        next_cursor = str(offset + len(items)) if offset + len(items) < len(filtered) else None
        return {
            "simulated": True,
            "items": items,
            "snapshot_token": token,
            "consistency": "source_snapshot",
            "next_cursor": next_cursor,
        }

    @app.get("/v1/studies", dependencies=[Depends(authenticate)])
    def studies(
        patient_id: str, hospital_id: str, modality: str, begin_time: str, end_time: str, encounter_id: str = ""
    ) -> dict:
        items = [study_fixture(joint) for joint in ("hip", "knee")]
        return {
            "simulated": True,
            "items": [
                row
                for row in items
                if row["patient_id"] == patient_id
                and row["hospital_id"] == hospital_id
                and row["modality"] == modality
                and (not encounter_id or row["encounter_id"] == encounter_id)
                and datetime.fromisoformat(begin_time)
                <= datetime.fromisoformat(row["checked_at"])
                <= datetime.fromisoformat(end_time)
            ],
        }

    @app.get("/v1/studies/{study_id}/series", dependencies=[Depends(authenticate)])
    def series(study_id: str) -> dict:
        if study_id not in {"study-hip", "study-knee"}:
            raise HTTPException(404, "Synthetic study not found")
        return {"items": [{"study_id": study_id, "series_id": study_id.replace("study", "series")}]}

    @app.get("/v1/series/{series_id}/images", dependencies=[Depends(authenticate)])
    def images(series_id: str) -> dict:
        if series_id not in {"series-hip", "series-knee"}:
            raise HTTPException(404, "Synthetic series not found")
        return {
            "items": [
                {
                    "study_id": series_id.replace("series", "study"),
                    "series_id": series_id,
                    "image_uid": f"{series_id}-image-{i}",
                    "url": f"https://dicom.invalid/{series_id}/{i}.dcm",
                }
                for i in (1, 2)
            ]
        }

    @app.get("/api/v2/study/list", dependencies=[Depends(authenticate_imaging)])
    def cloud_studies(
        system_patient_id: str,
        organ_code: str,
        chk_modality: str,
        begin_time: str,
        end_time: str,
        op_em_hp_ex_mark: str,
        op_em_hp_ex_no: str,
    ) -> dict:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(settings.imaging_timezone)
        begin = datetime.fromisoformat(begin_time).replace(tzinfo=zone).isoformat()
        end = datetime.fromisoformat(end_time).replace(tzinfo=zone).isoformat()
        result = studies(system_patient_id, organ_code, chk_modality, begin, end, op_em_hp_ex_no)
        data = [
            {
                "study_primary_id": row["study_id"],
                "ris_study_id": row["study_id"].replace("study", "ris"),
                "organ_code": row["hospital_id"],
                "system_patient_id": row["patient_id"],
                "op_em_hp_ex_mark": "3",
                "op_em_hp_ex_no": row["encounter_id"],
                "chk_modality": row["modality"],
                "proj_name": row["project_name"],
                "ckpt_name": row["body_part"],
                "chk_dt": datetime.fromisoformat(row["checked_at"]).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S"),
                "is_upload": 1,
                "image_type": "dicom",
            }
            for row in result["items"]
            if op_em_hp_ex_mark == "3"
        ]
        return {"code": 200, "data": data, "error": {"error_code": 0}, "simulated": True}

    @app.get("/api/v2/dicom/series-instance-uid", dependencies=[Depends(authenticate_imaging)])
    def cloud_series(study_primary_id: str) -> dict:
        result = series(study_primary_id)
        data = [
            {
                "series_id": row["series_id"],
                "organ_code": "synthetic-hospital",
                "pacs_study_id": f"pacs-{study_primary_id}",
                "pacs_series_id": f"pacs-{row['series_id']}",
                "series_number": 1,
                "chk_modality": "DR",
            }
            for row in result["items"]
        ]
        return {"code": 200, "data": data, "error": {"error_code": 0}, "simulated": True}

    @app.get("/api/v2/storage/dicom/sop-instance-uid", dependencies=[Depends(authenticate_imaging)])
    def cloud_images(series_id: str, url_type: str = "") -> dict:
        if url_type not in {"", "0", "1", "2", "3", "4"}:
            raise HTTPException(422, "Unsupported URL type")
        result = images(series_id)
        data = [
            {
                "sop_instance_uid": row["image_uid"],
                "series_instance_uid": f"dicom-{series_id}",
                "study_instance_uid": f"dicom-{row['study_id']}",
                "domain": "https://dicom.invalid",
                "file_path": f"/{series_id}/{index}.dcm?synthetic=1",
                "image_instance_number": index,
            }
            for index, row in enumerate(result["items"], start=1)
        ]
        return {"code": 200, "data": data, "error": {"error_code": 0}, "simulated": True}

    @app.post("/v1/recognitions", dependencies=[Depends(authenticate)])
    def recognize(body: dict) -> dict:
        return {
            "status": "completed",
            "raw_type": body["target_category"],
            "category": body["target_category"],
            "raw_count": "1",
            "count": "1",
            "count_scope": "study_group",
            "unit": body["unit"],
            "study_ids": body["study_ids"],
            "processed_uids": [item["image_uid"] for item in body["images"]],
            "excluded": {},
            "failed": {},
            "evidence": [f"synthetic-evidence:{body['request_id']}"],
            "counting_basis": "SYNTHETIC fixed group total; does not validate cross-image counting",
            "model_version": "synthetic-model-v1",
            "preprocessing_version": "not_performed",
            "model_job_id": f"demo-{body['request_id']}",
            "error": None,
            "simulated": True,
        }

    return app
