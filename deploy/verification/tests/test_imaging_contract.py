from datetime import timedelta

import httpx
import pytest
from langflow.verification.imaging import ImageCloudClient
from pydantic import SecretStr, ValidationError


def test_documented_study_primary_key_is_distinct_from_ris_id(settings):
    cloud = ImageCloudClient(settings, None)
    study = cloud.study(
        {
            "study_primary_id": "cloud-primary-1",
            "ris_study_id": "ris-record-2",
            "organ_code": "hospital-3",
            "system_patient_id": "patient-4",
            "op_em_hp_ex_mark": "3",
            "op_em_hp_ex_no": "visit-5",
            "chk_modality": "CT",
            "chk_dt": "2026-09-19 10:00:00",
            "proj_name": "hip",
            "ckpt_name": "hip",
        }
    )
    assert study.study_id == study.study_primary_id == "cloud-primary-1"
    assert study.ris_study_id == "ris-record-2"
    assert study.encounter_type == "inpatient"
    assert study.checked_at.utcoffset() == timedelta(hours=8)
    assert study.raw["system_patient_id"] == study.patient_id


def test_download_url_preserves_signed_query_and_separate_dicom_identifiers():
    image = ImageCloudClient.image(
        {
            "domain": "https://dicom.invalid",
            "file_path": "/bucket/file.dcm?signature=synthetic%2Ftest&expires=123",
            "sop_instance_uid": "1.2.3.4",
            "study_instance_uid": "1.2.3",
            "series_instance_uid": "1.2.3.1",
        },
        study_primary_id="cloud-primary-1",
        series_id="cloud-series-2",
    )
    assert image.study_id == "cloud-primary-1"
    assert image.series_id == "cloud-series-2"
    assert image.image_uid == "1.2.3.4"
    assert image.url == "https://dicom.invalid/bucket/file.dcm?signature=synthetic%2Ftest&expires=123"
    assert image.raw["series_instance_uid"] != image.series_id


@pytest.mark.parametrize("path", ["relative/file.dcm", "file:///tmp/image.dcm", "https://user:password@host/file.dcm"])
def test_unsupported_download_reference_fails_instead_of_guessing_a_host(path):
    with pytest.raises(ValidationError):
        ImageCloudClient.image(
            {"file_path": path, "sop_instance_uid": "1.2.3"}, study_primary_id="study-1", series_id="series-1"
        )


@pytest.mark.parametrize(
    "body",
    [
        {"code": 500, "data": []},
        {"code": 200, "data": [], "error": {"error_code": 7}},
        {"code": 200, "data": {}},
        {"items": []},
    ],
)
async def test_http_200_does_not_hide_business_or_contract_errors(settings, body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as http:
        with pytest.raises(ValueError, match="code/data"):
            await ImageCloudClient(settings, http).get("http://upstream/api/v2/study/list")


@pytest.mark.parametrize("url", ["http://upstream/api/v2/study/list", "http://other-cloud/api/v2/study/list"])
async def test_x_token_uses_only_imaging_credential_and_trusted_origin(settings, url):
    settings = settings.model_copy(update={"demo_mode": False})
    settings.imaging_token = SecretStr("separate-cloud-token")
    requests = []

    def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as http:
        await ImageCloudClient(settings, http).get(url + "?url_type=4", params={"system_patient_id": "patient-1"})
    assert len(requests) == 1
    assert requests[0].url.params["url_type"] == "4"
    assert requests[0].url.params["system_patient_id"] == "patient-1"
    assert "authorization" not in requests[0].headers
    assert requests[0].headers.get("x-token") == ("separate-cloud-token" if "//upstream/" in url else None)
