# ruff: noqa: INP001, S101, PLR2004, F811 - synthetic observation contract regressions and shared fixture.
"""Exercise the imaging adapter, result checks and numeric comparison together."""

import json
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jsonschema
import pyarrow as pa
import pytest
from langflow.business.catalog import CATALOG
from langflow.business.datasets import DatasetStore
from langflow.business.runtime import Runtime
from langflow.business.templates import templates
from test_workflows import env  # noqa: F401


def configs():
    graph = next(t["graph"] for t in templates() if t["id"] == "hip_knee_core")
    return {n["id"]: deepcopy(n["config"]) for n in graph["nodes"]}


def test_imaging_contract_has_no_expected_quantity_or_unit_inputs():
    schema = CATALOG["imaging"]["schema"]
    config = configs()["Observation"]
    config["connection"] = "fixture-service"
    jsonschema.validate(config, schema)
    for key in ("quantity_field", "unit_field", "unit_value"):
        assert key not in schema["properties"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**config, key: "CNT"}, schema)
    assert "unit" not in configs()["Results"]["columns"]


@pytest.mark.parametrize("unit", [None, "件", "套"])
@pytest.mark.parametrize("quantity", [1, 2])
def test_observation_compares_without_unit_gate(env, monkeypatch, unit, quantity):
    runtime, source, sent = setup_runtime(env, monkeypatch, quantity=quantity, unit=unit)
    cfg = configs()
    observed = runtime.run_node(
        {"id": "Observation", "kind": "imaging", "config": cfg["Observation"]}, {"data": [source]}
    )
    assert observed["data"]["row_count"] == 1
    assert observed["issues"]["row_count"] == 0
    assert set(sent[0]) == {"hospital", "patient", "encounter", "category", "evidence", "evidence_context"}
    assert json.loads(sent[0]["evidence_context"])[0]["RPT_NO"] == "MOCK-RPT"
    compared = runtime.run_node(
        {"id": "Compare", "kind": "compare", "config": cfg["Compare"]}, {"data": [observed["data"]]}
    )
    row = runtime.store.page(compared["data"]["id"])["rows"][0]
    assert row["observed_unit"] == unit
    assert "unit" not in row
    assert Decimal(str(row["settled_amount"])) == 20000
    assert Decimal(str(row["observed_amount"])) == quantity * 10000
    expected = "equal" if quantity == 2 else "different"
    assert row["quantity_status"] == row["amount_status"] == expected
    assert row["category_status"] == "equal"


@pytest.mark.parametrize(
    "overrides",
    [
        {"coverage_confirmed": False},
        {"recognition_confirmed": False},
        {"recognized_quantity": -1},
        {"recognized_quantity": None},
        {"evidence_ref": None},
    ],
)
def test_observation_keeps_evidence_and_result_checks(env, monkeypatch, overrides):
    runtime, source, _ = setup_runtime(env, monkeypatch, overrides=overrides)
    result = runtime.run_node(
        {"id": "Observation", "kind": "imaging", "config": configs()["Observation"]},
        {"data": [source]},
    )
    assert result["data"]["row_count"] == 0
    assert result["issues"]["row_count"] == 1


def setup_runtime(env, monkeypatch, *, quantity=1, unit=None, overrides=None):
    database, settings = env
    runtime = object.__new__(Runtime)
    runtime.store = DatasetStore(database, str(uuid4()))
    runtime.database, runtime.settings = database, settings
    runtime.prefix, runtime.parameters = "", {}
    runtime.connection = lambda _: SimpleNamespace(id=str(uuid4()))
    row = {
        "ORGAN_CODE": "MOCK-HOSPITAL",
        "PSN_NO": "MOCK-PATIENT",
        "OP_EM_NO": "MOCK-VISIT",
        "target_category": "人工髋关节",
        "CNT": 2,
        "PRIC": 10000,
        "_representative_row_id": 0,
        "image_manifest": '["https://fixture.invalid/image"]',
        "image_manifest_context": '[{"RPT_NO":"MOCK-RPT"}]',
    }
    table = pa.Table.from_pylist([row])
    source = runtime.store.write_batches("Images", [[row]], table.schema)
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        result = {
            "recognized_category": "人工髋关节",
            "recognized_quantity": quantity,
            "coverage_confirmed": True,
            "recognition_confirmed": True,
            "evidence_ref": "synthetic:test",
            "simulated": True,
            **(overrides or {}),
        }
        if unit is not None:
            result["observed_unit"] = unit
        return httpx.Response(200, json=result)

    monkeypatch.setattr(
        "langflow.business.sources.client_for",
        lambda *_: httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(respond)),
    )
    return runtime, source, sent
