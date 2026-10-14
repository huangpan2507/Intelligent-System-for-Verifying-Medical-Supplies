# ruff: noqa: INP001, RUF001, S101, F811, PLR2004, PT018 - fixture tests use synthetic Chinese data and explicit assertions.
"""Core-path regressions for compact capabilities; no paid requests or extra business scenario."""

import json
from copy import deepcopy
from datetime import timezone
from types import SimpleNamespace
from uuid import uuid4

import duckdb
import httpx
import pyarrow as pa
import pytest
from langflow.business import classification, collection
from langflow.business.datasets import ROW_ID, DatasetStore
from langflow.business.lookup import lookup_query
from langflow.business.relational import unary_query
from langflow.business.templates import templates
from test_workflows import env  # noqa: F401


def config(name):
    graph = next(t["graph"] for t in templates() if t["id"] == "hip_knee_core")
    return deepcopy(next(n["config"] for n in graph["nodes"] if n["id"] == name))


def material(product, surgery="人工全膝关节置换术"):
    return {
        "HILIST_NAME": surgery,
        "PRODNAME": product,
        "HOS_PROJ_NAME": product,
        "MEDINS_LIST_NAME": product,
        "SPEC": "模拟套",
        "CNT": 1,
        "PRIC": 5000,
    }


@pytest.mark.parametrize(
    ("product", "surgery", "expected"),
    [
        ("人工髋关节（模拟）", "人工全髋关节置换术", "人工髋关节"),
        ("人工膝关节（模拟）", "人工全膝关节置换术", "人工膝关节"),
        ("膝关节假体系统", "人工全膝关节置换术", "无法确定"),
        ("人工髋关节（模拟）", "人工全膝关节置换术", "无法确定"),
        (None, None, "无法确定"),
    ],
)
def test_rule_classification_preserves_material_facts(product, surgery, expected):
    row = material(product, surgery)
    with duckdb.connect() as db:
        schema = pa.schema(
            [(f, pa.string()) for f in classification.effective_config(config("Classification"))["input_fields"]]
            + [("CNT", pa.int64()), ("PRIC", pa.int64())]
        )
        db.register("source", pa.Table.from_pylist([row], schema=schema))
        result = (
            db.execute(classification.rule_query(config("Classification"), "source")).fetch_arrow_table().to_pylist()[0]
        )
    assert result["target_category"] == expected
    assert all(result[k] == v for k, v in row.items())


@pytest.mark.parametrize("quote", ["膝关节假体系统", "输入中不存在的耗材"])
def test_only_unresolved_records_call_model_and_quotes_are_checked(env, monkeypatch, quote):
    db, settings = env
    store = DatasetStore(db, str(uuid4()))
    rows = [material("人工膝关节（模拟）"), material("膝关节假体系统")]
    source = store.write_batches("source", [rows], pa.Table.from_pylist(rows).schema)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        result = {
            "model_category": "人工膝关节",
            "model_reason": "耗材描述为膝关节假体系统",
            "model_evidence_field": "PRODNAME",
            "model_evidence_text": quote,
            "model_confidence": 0.05,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]})

    monkeypatch.setattr(
        "langflow.business.sources.client_for",
        lambda *_: httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(respond)),
    )
    runtime = SimpleNamespace(
        store=store, settings=settings, prefix="", connection=lambda _: SimpleNamespace(id=str(uuid4()))
    )
    outputs = classification.execute(runtime, {"id": "Classification", "config": config("Classification")}, source)
    assert len(calls) == 1
    assert json.loads(calls[0]["messages"][1]["content"])["PRODNAME"] == "膝关节假体系统"
    expected = 2 if quote == "膝关节假体系统" else 1
    assert outputs["data"]["row_count"] == expected
    assert outputs["issues"]["row_count"] == 2 - expected
    assert store.page(outputs["data"]["id"])["rows"][0]["CNT"] == 1
    if expected == 2:
        assert any(
            float(r["classification_confidence"] or 0) == 0.05 for r in store.page(outputs["data"]["id"])["rows"]
        )


def test_lookup_keeps_hospital_system_scope_and_parses_actual_time():
    left = [{"hospital": "H1", "system": "RIS1", "rpt": "R1", "CNT": 1, ROW_ID: 9}]
    right = [
        {"hospital": hospital, "system": system, "rpt": "R1", "chk_dt": "2026-09-01 09:01:23", ROW_ID: i}
        for i, (hospital, system) in enumerate([("H1", "RIS1"), ("H2", "RIS1"), ("H1", "RIS2")])
    ]
    cfg = {
        "keys": [{"left": f, "right": f} for f in ["hospital", "system", "rpt"]],
        "returns": [{"field": "chk_dt", "output": "checked_at", "type": "datetime", "timezone": "Asia/Shanghai"}],
    }
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist(left))
        db.register("remote", pa.Table.from_pylist(right))
        query = lookup_query(cfg, "source", list(left[0]), "remote")
        rows = db.execute(query).fetch_arrow_table().to_pylist()
    assert len(rows) == 1 and rows[0]["CNT"] == 1
    assert rows[0]["checked_at"].astimezone(timezone.utc).isoformat() == "2026-09-01T01:01:23+00:00"
    assert rows[0]["_lookup_input_row_id"] == 9


def test_multiple_images_collect_into_one_unit_and_incomplete_calls_do_not_pass():
    cfg = {
        "collection": {
            "group_by": ["detail"],
            "retain_fields": ["CNT", "PRIC"],
            "address_fields": ["domain", "file_path"],
            "item_keys": ["sop"],
            "output": "manifest",
        }
    }
    inputs = [{"detail": "MOCK-DETAIL", "CNT": 1, "PRIC": 5000, ROW_ID: i} for i in range(2)]
    raw = [
        {"domain": "https://mock.invalid", "file_path": "/" + str(i), "sop": str(i), "_request_row_id": i, ROW_ID: i}
        for i in range(2)
    ]
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist(inputs))
        db.register("raw", pa.Table.from_pylist(raw))
        db.execute("CREATE TABLE issues (_request_row_id BIGINT)")
        query = collection.collection_query(cfg, "source", "raw", "issues")
        rows = db.execute(query).fetch_arrow_table().to_pylist()
        assert len(rows) == 1 and rows[0]["CNT"] == 1 and rows[0]["PRIC"] == 5000
        assert len(json.loads(rows[0]["manifest"])) == 2 and not rows[0]["_issue_reason"]
        db.execute("INSERT INTO issues VALUES (1)")
        assert db.execute(query).fetch_arrow_table().to_pylist()[0]["_issue_reason"] == "incomplete_api_request"


def test_compare_computes_independent_observed_amount_and_names_results():
    cfg = config("Compare")
    source = {
        "_representative_row_id": 0,
        "CNT": 2,
        "PRIC": 5000,
        "recognized_quantity": 1,
        "target_category": "人工膝关节",
        "recognized_category": "人工膝关节",
        ROW_ID: 0,
    }
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist([source]))
        query = unary_query("compare", cfg, "source", list(source))["data"]
        result = db.execute(query).fetch_arrow_table().to_pylist()[0]
    assert result["settled_amount"] == 10000 and result["observed_amount"] == 5000
    assert result["category_status"] == "equal"
    assert result["quantity_status"] == result["amount_status"] == "different"
    assert result["CNT"] == 2 and result["PRIC"] == 5000


def test_compact_template_keeps_eleven_steps_and_requires_real_connection_bindings():
    graph = next(t["graph"] for t in templates() if t["id"] == "hip_knee_core")
    assert len(graph["nodes"]) == 11 and len(graph["edges"]) == 10
    assert len({n["kind"] for n in graph["nodes"]}) == 9
    assert all(n["config"]["connection"] == "" for n in graph["nodes"] if "connection" in n["config"])
