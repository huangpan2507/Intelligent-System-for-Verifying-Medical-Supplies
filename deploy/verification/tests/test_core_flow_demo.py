import json
from pathlib import Path

import httpx
import pytest
from langflow.business.core_flow_demo import create_core_flow_app, inspection_cases
from langflow.verification.demo import create_demo_app

FIXTURES = Path(__file__).resolve().parents[2] / "business/fixtures/core-flow"
CONTRACTS = json.loads((FIXTURES / "imaging-api-contracts.json").read_text())
SETTLEMENTS = json.loads((FIXTURES / "settlement-rows.json").read_text())["rows"]


@pytest.fixture
async def cloud(settings):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_core_flow_app(settings)),
        base_url="http://upstream",
        headers={"X-Token": settings.upstream_token.get_secret_value()},
    ) as client:
        yield client


def assert_contract(response, contract):
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200 and body["error"]["error_code"] == 0
    assert body["simulated"] is True
    kinds = {"string": str, "number": (int, float), "integer": int, "array": list, "object": dict, "Null": type(None)}
    for field in contract["success_response_fields"]:
        values = [body]
        for part in field["key"].split("."):
            values = [item for value in values for item in (value if isinstance(value, list) else [value])]
            assert all(part in value for value in values), field["key"]
            values = [value[part] for value in values]
        assert all(isinstance(value, kinds[field["field_type"]]) for value in values), field["key"]
    return body["data"]


@pytest.mark.parametrize("settlement", SETTLEMENTS, ids=["hip", "knee"])
async def test_database_identity_to_documented_api_chain_and_independent_observation(cloud, settlement):
    joint = settlement["SETL_FEE_LIST_ID"].removeprefix("MOCK-DETAIL-")
    cases = [c for c in inspection_cases() if c["joint"] == joint]
    manifest, context = [], []
    for case in cases:
        images = assert_contract(
            await cloud.get(CONTRACTS[2]["path"], params={"series_id": case["series_id"], "url_type": "3"}),
            CONTRACTS[2],
        )
        assert len(images) == (3 if case["modality"] == "CT" else 2)
        for row in images:
            address = row["domain"] + row["file_path"]
            manifest.append(address)
            context.append(
                {
                    "address": address,
                    "series_id": case["series_id"],
                    "series_modality": case["modality"],
                    "study_exam_part": case["code"],
                }
            )
    assert {c["series_modality"] for c in context} == {"DR", "CT"}
    assert len(manifest) == len(set(manifest))
    payload = {
        "patient": settlement["PSN_NO"],
        "hospital": settlement["ORGAN_CODE"],
        "encounter": settlement["OP_EM_NO"],
        "category": "deliberately wrong target",
        "quantity": 999,
        "unit": "deliberately wrong unit",
        "evidence": json.dumps(manifest),
        "evidence_context": json.dumps(context),
    }
    response = await cloud.post("/business/core-flow/imaging", json=payload)
    assert response.status_code == 200
    observation = response.json()
    assert observation["recognized_quantity"] == "1"
    assert observation["observed_unit"] == "套"
    assert observation["recognized_category"] == {"HIP": "人工髋关节", "KNEE": "人工膝关节"}[joint]
    assert observation["coverage_confirmed"] is True and observation["simulated"] is True
    partial = await cloud.post("/business/core-flow/imaging", json={**payload, "evidence": json.dumps(manifest[:1])})
    assert partial.json()["coverage_confirmed"] is False
    assert partial.json()["recognized_quantity"] is None
    mismatched = [{**c, "study_exam_part": "B99999999"} for c in context]
    wrong = await cloud.post(
        "/business/core-flow/imaging", json={**payload, "evidence_context": json.dumps(mismatched)}
    )
    assert wrong.json()["coverage_confirmed"] is False


@pytest.mark.parametrize(
    "wrong",
    [
        {"name": "unknown"},
        {"cardno": "unknown"},
        {"organ_code": "unknown"},
        {"op_em_hp_ex_no": "unknown"},
        {"chk_modality": "CT"},
        {"begin_time": "2025-08-20 00:00:00"},
    ],
)
async def test_query_filters_do_not_return_an_unrelated_study(cloud, wrong):
    response = await cloud.get(
        CONTRACTS[0]["path"],
        params={
            "begin_time": "2025-08-13 00:00:00",
            "end_time": "2025-08-20 23:59:59",
            "cardno": "MOCK-CARD-HIP",
            **wrong,
        },
    )
    assert response.status_code == 200 and response.json()["data"] == []


async def test_documented_minimum_and_time_boundaries(cloud):
    params = {"begin_time": "2025-08-19 10:00:00", "end_time": "2025-08-19 10:00:00"}
    assert (await cloud.get(CONTRACTS[0]["path"], params=params)).status_code == 200
    response = await cloud.get(CONTRACTS[0]["path"], params={**params, "cardno": "MOCK-CARD-HIP"})
    assert len(response.json()["data"]) == 1
    assert (await cloud.get(CONTRACTS[0]["path"], params={**params, "page": "1"})).status_code == 422
    assert (await cloud.get(CONTRACTS[0]["path"], params={**params, "begin_time": "invalid"})).status_code == 422
    assert (
        await cloud.get(CONTRACTS[0]["path"], params={**params, "begin_time": "2025-08-20 00:00:00"})
    ).status_code == 422


async def test_x_token_is_required(cloud):
    response = await cloud.get(
        CONTRACTS[0]["path"],
        params={
            "begin_time": "2025-08-13 00:00:00",
            "end_time": "2025-08-20 23:59:59",
        },
        headers={"X-Token": "wrong"},
    )
    assert response.status_code == 401


async def test_legacy_fixture_chain_still_works(settings):
    params = {
        "begin_time": "2025-08-13 00:00:00",
        "end_time": "2025-08-20 23:59:59",
        "system_patient_id": "synthetic-patient-knee",
        "organ_code": "synthetic-hospital",
        "chk_modality": "DR",
        "op_em_hp_ex_mark": "3",
        "op_em_hp_ex_no": "synthetic-visit-knee",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_demo_app(settings)),
        base_url="http://upstream",
        headers={"X-Token": settings.upstream_token.get_secret_value()},
    ) as client:
        studies = (await client.get(CONTRACTS[0]["path"], params=params)).json()["data"]
        assert [row["study_primary_id"] for row in studies] == ["study-knee"]
        series = (await client.get(CONTRACTS[1]["path"], params={"study_primary_id": "study-knee"})).json()["data"]
        images = (await client.get(CONTRACTS[2]["path"], params={"series_id": series[0]["series_id"]})).json()["data"]
        assert len(images) == 2
