"""Controlled hip/knee fixtures; no real patient data, DICOM files or trained model."""

import json
import secrets
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from langflow.verification.settings import MIN_TOKEN_LENGTH, FlowSettings

HOSPITAL = "MOCKHOSP0000000001"


def create_core_flow_app(settings: FlowSettings | None = None) -> FastAPI:
    settings = settings or FlowSettings()
    token = settings.imaging_token.get_secret_value() or settings.upstream_token.get_secret_value()
    if not settings.demo_mode or len(token) < MIN_TOKEN_LENGTH:
        msg = "Core fixtures require demo mode and a configured imaging credential"
        raise ValueError(msg)

    def authenticate(x_token: str = Header(alias="X-Token")):
        if not secrets.compare_digest(x_token, token):
            raise HTTPException(401, "Invalid synthetic image cloud credential")

    app = FastAPI(title="SYNTHETIC Business core flow API")

    @app.get("/api/v2/study/list", dependencies=[Depends(authenticate)])
    def studies(
        request: Request,
        begin_time: str,
        end_time: str,
        name: str = "",
        cardno: str = "",
        organ_code: str = "",
        system_patient_id: str = "",
        chk_modality: str = "",
        op_em_hp_ex_mark: str = "",
        op_em_hp_ex_no: str = "",
    ):
        filters = {
            "name": name,
            "organ_code": organ_code,
            "system_patient_id": system_patient_id,
            "chk_modality": chk_modality,
            "op_em_hp_ex_mark": op_em_hp_ex_mark,
            "op_em_hp_ex_no": op_em_hp_ex_no,
        }
        if set(request.query_params) - {"begin_time", "end_time", "cardno", *filters}:
            raise HTTPException(
                422, "Unsupported synthetic query option; this fixture returns its complete bounded list"
            )
        zone = ZoneInfo("Asia/Shanghai")
        try:
            begin, end = [
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=zone) for value in (begin_time, end_time)
            ]
        except ValueError as exc:
            raise HTTPException(422, "Times must use YYYY-MM-DD HH:mm:ss in Asia/Shanghai") from exc
        if begin > end:
            raise HTTPException(422, "Start must not follow end")
        cards = {f"MOCK-STUDY-{joint}": f"MOCK-CARD-{joint}" for joint in ("HIP", "KNEE")}
        return envelope(
            [
                row
                for row in study_rows()
                if all(not value or row[key] == value for key, value in filters.items())
                and (not cardno or cards[row["study_primary_id"]] == cardno)
                and begin <= datetime.strptime(row["chk_dt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=zone) <= end
            ]
        )

    @app.get("/api/v2/dicom/series-instance-uid", dependencies=[Depends(authenticate)])
    def series(study_primary_id: str):
        if study_primary_id not in {"MOCK-STUDY-HIP", "MOCK-STUDY-KNEE"}:
            raise HTTPException(404, "Unknown synthetic study")
        return envelope(series_rows(study_primary_id))

    @app.get("/api/v2/storage/dicom/sop-instance-uid", dependencies=[Depends(authenticate)])
    def images(series_id: str, url_type: str = ""):
        if url_type not in {"", "0", "1", "2", "3", "4"}:
            raise HTTPException(422, "Unsupported URL type")
        if series_id not in {c["series_id"] for c in inspection_cases()}:
            raise HTTPException(404, "Unknown synthetic series")
        return envelope(image_rows(series_id))

    register_observation(app, authenticate)
    return app


def envelope(rows):
    trace = uuid4().hex
    return {
        "code": 200,
        "message": "Synthetic fixture response",
        "data": rows,
        "error": {"error_code": 0},
        "meta": {"trace": dict.fromkeys(("trace_id", "parent_id", "span_id", "request_id"), trace)},
        "simulated": True,
    }


def study_rows():
    return [
        {
            "study_primary_id": f"MOCK-STUDY-{joint}",
            "ris_study_id": f"MOCK-RIS-{joint}",
            "organ_code": HOSPITAL,
            "organ_name": "核心流程模拟医院",
            "system_patient_id": f"MOCK-CLOUD-PATIENT-{joint}",
            "name": name,
            "sex": "9",
            "age": "60",
            "op_em_hp_ex_mark": "3",
            "op_em_hp_ex_no": f"MOCK-VISIT-{joint}",
            "chk_modality": "DR",
            "chk_status": 10,
            "image_type": "dicom",
            "is_upload": 1,
            "is_report": 0,
            "proj_name": f"{part}正侧位(模拟)",
            "chk_methodname": "模拟DR检查",
            "ckpt_name": part,
            "chk_dt": "2025-08-19 10:00:00",
            "chk_doc_name": "模拟检查医生",
            "report_list": [],
            "thumb_images": None,
        }
        for joint, part, name in [("HIP", "髋关节", "模拟患者甲"), ("KNEE", "膝关节", "模拟患者乙")]
    ]


def series_rows(study_id):
    return [
        {
            "series_id": study_id.replace("STUDY", "SERIES"),
            "organ_code": HOSPITAL,
            "pacs_study_id": study_id.replace("STUDY", "PACS-STUDY"),
            "pacs_series_id": study_id.replace("STUDY", "PACS-SERIES"),
            "series_number": 1,
            "chk_modality": "DR",
        }
    ]


def inspection_cases():
    """Controlled evidence, including four joint/modality combinations and a broader rule fallback."""
    return [
        {
            "joint": joint,
            "suffix": suffix,
            "modality": modality,
            "code": code,
            "series_id": f"MOCK-SERIES-{joint}{suffix}",
            "study_id": f"MOCK-RIS-{joint}{suffix}",
            "description": description,
        }
        for joint, suffix, modality, code, description in [
            ("HIP", "", "DR", "BQ02ZZZ00", "模拟髋关节正位检查"),
            ("KNEE", "", "DR", "BQ07ZZZ00", "模拟右侧膝关节检查"),
            ("HIP", "-CT", "CT", "BQ20ZUZZZ", "模拟右侧髋关节 CT 检查"),
            ("KNEE", "-CT", "CT", "BQ27ZUZZZ", "模拟右侧膝关节 CT 检查"),
            ("HIP", "-NEAR", "DR", "BQ03ZZ900", "模拟右侧股骨近端检查,采集范围包含髋关节;影像可用性待识别确认"),
        ]
    ]


def image_rows(series_id):
    cases = inspection_cases()
    case = next(c for c in cases if c["series_id"] == series_id)
    joint_id = cases.index(case) + 1
    return [
        {
            "image_instance_number": index,
            "file_path": f"/core-flow/{series_id}/{index}.dcm?signature=synthetic%2F{index}&expires=0",
            "file_size": "1024",
            "domain": "https://dicom.invalid",
            "study_instance_uid": f"2.25.20261012.{joint_id}",
            "series_instance_uid": f"2.25.20261012.{joint_id}.1",
            "sop_instance_uid": f"2.25.20261012.{joint_id}.1.{index}",
            "file_suffix": "dcm",
        }
        for index in range(1, 4 if case["modality"] == "CT" else 3)
    ]


def register_observation(app, authenticate):
    @app.post("/business/core-flow/imaging", dependencies=[Depends(authenticate)])
    def observe(body: dict):
        # The observation depends on fixture identity/evidence, never the requested category or CNT.
        joint = {"MOCK-PATIENT-HIP": "HIP", "MOCK-PATIENT-KNEE": "KNEE"}.get(body.get("patient"))
        if not joint or body.get("hospital") != HOSPITAL or body.get("encounter") != f"MOCK-VISIT-{joint}":
            raise HTTPException(422, "Unknown synthetic observation scope")
        try:
            manifest = json.loads(body.get("evidence") or "[]")
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Evidence must be a JSON array of image references") from exc
        # Synthetic coverage is checked against known complete series, never inferred from a text classification.
        groups = [
            {row["domain"] + row["file_path"] for row in image_rows(case["series_id"])}
            for case in inspection_cases()
            if case["joint"] == joint
        ]
        received = set(manifest) if isinstance(manifest, list) and all(isinstance(p, str) for p in manifest) else set()
        covered = bool(received) and len(received) == len(manifest) and received <= set().union(*groups)
        covered = covered and all(not received.intersection(group) or group <= received for group in groups)
        if body.get("evidence_context") is not None:
            try:
                context = json.loads(body["evidence_context"])
                expected = {
                    row["domain"] + row["file_path"]: case
                    for case in inspection_cases()
                    if case["joint"] == joint
                    for row in image_rows(case["series_id"])
                }
                covered = (
                    covered
                    and {item["address"] for item in context} == received
                    and all(
                        item["series_id"] == expected[item["address"]]["series_id"]
                        and item["series_modality"] == expected[item["address"]]["modality"]
                        and item["study_exam_part"] == expected[item["address"]]["code"]
                        for item in context
                    )
                )
            except (KeyError, TypeError, ValueError):
                covered = False
        return {
            "recognized_category": {"HIP": "人工髋关节", "KNEE": "人工膝关节"}[joint] if covered else None,
            "recognized_quantity": "1" if covered else None,
            "observed_unit": "套" if covered else None,
            "coverage_confirmed": covered,
            "recognition_confirmed": covered,
            "evidence_ref": f"synthetic-core-observation:{joint}:v1" if covered else None,
            "simulated": True,
        }
