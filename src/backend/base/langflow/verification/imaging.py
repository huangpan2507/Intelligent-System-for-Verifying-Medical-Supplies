"""Adapter for the three documented image-cloud OpenAPI endpoints."""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx

from langflow.verification.schemas import ImageRef, Study

if TYPE_CHECKING:
    from langflow.verification.settings import FlowSettings

STUDIES_PATH = "/api/v2/study/list"
SERIES_PATH = "/api/v2/dicom/series-instance-uid?study_primary_id={study_primary_id}"
IMAGES_PATH = "/api/v2/storage/dicom/sop-instance-uid?series_id={series_id}"
ENCOUNTER_CODES = {"outpatient": "1", "inpatient": "3"}


class ImageCloudClient:
    def __init__(self, settings: FlowSettings, http: httpx.AsyncClient):
        self.settings, self.http = settings, http
        self.timezone = ZoneInfo(settings.imaging_timezone)

    async def get(self, url: str, *, params: dict | None = None) -> list[dict]:
        target, trusted = httpx.URL(url), httpx.URL(self.settings.imaging_url)
        token = self.settings.imaging_token.get_secret_value()
        if not token and self.settings.demo_mode:
            token = self.settings.upstream_token.get_secret_value()
        headers = {}
        if token and (target.scheme, target.host, target.port) == (trusted.scheme, trusted.host, trusted.port):
            headers["X-Token"] = token
        response = await self.http.get(
            url,
            params=httpx.QueryParams(target.query).merge(params or {}),
            headers=headers,
            timeout=self.settings.request_timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
        if (
            not isinstance(body, dict)
            or body.get("code") != HTTPStatus.OK
            or not isinstance(body.get("error", {}), dict)
            or body.get("error", {}).get("error_code", 0) != 0
            or not isinstance(body.get("data"), list)
            or not all(isinstance(item, dict) for item in body["data"])
        ):
            msg = "Image cloud returned an unsuccessful or invalid code/data response"
            raise ValueError(msg)
        return body["data"]

    def study(self, raw: dict) -> Study:
        checked_at = datetime.fromisoformat(raw["chk_dt"]) if raw.get("chk_dt") else None
        if checked_at is not None and checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=self.timezone)
        return Study(
            study_id=raw["study_primary_id"],
            study_primary_id=raw["study_primary_id"],
            ris_study_id=raw.get("ris_study_id"),
            patient_id=raw.get("system_patient_id"),
            hospital_id=raw.get("organ_code"),
            encounter_id=raw.get("op_em_hp_ex_no"),
            encounter_type={"1": "outpatient", "3": "inpatient"}.get(str(raw.get("op_em_hp_ex_mark"))),
            modality=raw.get("chk_modality"),
            checked_at=checked_at,
            project_name=raw.get("proj_name"),
            body_part=raw.get("ckpt_name"),
            raw=raw,
        )

    @staticmethod
    def image(raw: dict, *, study_primary_id: str, series_id: str) -> ImageRef:
        path = raw["file_path"]
        if not isinstance(path, str) or not path:
            msg = "Image cloud response has no DICOM file_path"
            raise ValueError(msg)
        # A relative path needs the response's domain; never guess the download host.
        url = urljoin(raw.get("domain") or "", path)
        return ImageRef(
            study_id=study_primary_id,
            series_id=series_id,
            image_uid=raw["sop_instance_uid"],
            url=url,
            raw=raw,
        )
