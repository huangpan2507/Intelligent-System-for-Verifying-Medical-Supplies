# ruff: noqa: INP001, S101, F811, PLR2004, RUF001, PT018, S608 - controlled source and model fixtures.
"""Code interpretation, repeated classification, candidate decisions and evidence grouping."""

import json
from types import SimpleNamespace
from uuid import uuid4

import duckdb
import httpx
import pyarrow as pa
import pytest
from langflow.business import classification, code_dictionary
from langflow.business.collection import collection_query
from langflow.business.coverage import audit
from langflow.business.datasets import DatasetStore
from langflow.business.templates import templates
from test_workflows import env  # noqa: F401


def config():
    graph = next(t["graph"] for t in templates() if t["id"] == "hip_knee_core")
    return next(n["config"] for n in graph["nodes"] if n["id"] == "StudyRelevance")


def record(code, target="人工髋关节", description="模拟检查"):
    return {
        "study_exam_part": code,
        "target_category": target,
        "classification_method": "rule",
        "classification_reason": "material_evidence",
        "classification_disposition": "continue",
        "study_chk_desc": description,
        "study_proj_name": "模拟项目",
        "study_ckpt_name": "下肢",
        "study_chk_modality": "CT" if code[2:3] == "2" else "DR",
        "CNT": 1,
        "PRIC": 10000,
    }


@pytest.mark.parametrize(
    ("code", "target", "expected"),
    [
        ("BQ02ZZZ00", "人工髋关节", "候选相关"),
        ("BQ20ZUZZZ", "人工髋关节", "候选相关"),
        ("BQ07ZZZ00", "人工膝关节", "候选相关"),
        ("BQ27ZUZZZ", "人工膝关节", "候选相关"),
        ("BQ27ZUZZZ", "人工髋关节", "明确无关"),
        ("BQ2FZUZZZ", "人工髋关节", "无法确定"),
        ("BQ08ZZZA", "人工膝关节", "无法确定"),
        ("B99999999", "人工膝关节", "无法确定"),
    ],
)
def test_exact_dictionary_and_target_specific_rules(code, target, expected):
    cfg, row = config(), record(code, target)
    classification.validate_config(cfg, list(row))
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist([row]))
        prepared = code_dictionary.query(cfg, "source")
        result = db.execute(classification.rule_query(cfg, f"({prepared})")).to_arrow_table().to_pylist()[0]
    assert result["study_relevance"] == expected
    assert all(result[key] == value for key, value in row.items())
    if expected != "无法确定":
        assert result["study_relevance_code_status"] == "resolved"
        assert "printed_page" in result["study_relevance_code_source"]


def test_repeated_classification_calls_model_only_for_resolved_ambiguous_text(env, monkeypatch):
    db, settings = env
    store = DatasetStore(db, str(uuid4()))
    rows = [
        record("BQ20ZUZZZ"),
        record("BQ03ZZ900", description="采集范围包含髋关节"),
        record("BQ2FZUZZZ"),
        record("B99999999"),
    ]
    source = store.write_batches("source", [rows], pa.Table.from_pylist(rows).schema)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        answer = {
            "model_category": "候选相关",
            "model_reason": "检查描述支持候选，实际覆盖尚待确认",
            "model_evidence_field": "study_chk_desc",
            "model_evidence_text": "采集范围包含髋关节",
            "model_confidence": 0.7,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    monkeypatch.setattr(
        "langflow.business.sources.client_for",
        lambda *_: httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(respond)),
    )
    runtime = SimpleNamespace(
        store=store, settings=settings, prefix="", connection=lambda _: SimpleNamespace(id=str(uuid4()))
    )
    output = classification.execute(runtime, {"id": "StudyRelevance", "config": config()}, source)
    assert len(calls) == 1
    assert output["data"]["row_count"] == output["issues"]["row_count"] == 2
    candidates = store.page(output["data"]["id"])["rows"]
    assert {r["study_relevance_method"] for r in candidates} == {"rule", "model"}
    assert all(r["target_category"] == "人工髋关节" and r["CNT"] == 1 for r in candidates)
    issues = store.page(output["issues"]["id"])["rows"]
    assert all(r["study_relevance_disposition"] == "uncompared" for r in issues)
    assert all(r["study_relevance_reason"] == "unresolved_dictionary_code" for r in issues)


def test_collection_preserves_per_image_context_without_multiplying_material():
    cfg = {
        "collection": {
            "group_by": ["detail"],
            "retain_fields": ["CNT"],
            "address_fields": ["base_url", "path"],
            "item_keys": ["image_id"],
            "output": "images",
            "item_context": ["RPT_NO", "series_id", "modality", "code"],
        }
    }
    with duckdb.connect() as db:
        db.execute(
            "CREATE TABLE source AS SELECT 0 _business_row_id, 'a' detail, 1 CNT, "
            "'s1' series_id, 'DR' modality, 'c1' code, 'request-a' RPT_NO "
            "UNION ALL SELECT 1, 'a', 1, 's2', 'CT', 'c2', 'request-a'"
        )
        db.execute(
            "CREATE TABLE raw AS SELECT 0 _business_row_id, 0 _request_row_id, "
            "'https://fixture.invalid' base_url, '/1' path, 'i1' image_id "
            "UNION ALL SELECT 1, 1, 'https://fixture.invalid', '/2', 'i2'"
        )
        db.execute("CREATE TABLE issues (_request_row_id BIGINT)")
        result = db.execute(collection_query(cfg, "source", "raw", "issues")).to_arrow_table().to_pylist()
    assert len(result) == 1 and result[0]["CNT"] == 1 and not result[0]["_issue_reason"]
    context = json.loads(result[0]["images_context"])
    assert {r["RPT_NO"] for r in context} == {"request-a"}
    assert {(r["series_id"], r["modality"], r["code"]) for r in context} == {("s1", "DR", "c1"), ("s2", "CT", "c2")}


def test_unusable_exam_is_only_a_fallback_for_material_without_a_result(env):
    database, _ = env
    store = DatasetStore(database, str(uuid4()))
    source = store.write_batches(
        "Settlements",
        [[{"detail": "a"}, {"detail": "b"}]],
        pa.schema([("detail", pa.string())]),
        provenance={"completeness": {"state": "complete"}},
    )
    units = classification.save_projection(
        store,
        "Checks",
        f"SELECT *, detail AS _identity FROM {store.relation(source['id'])}",
        source,
    )
    results = classification.save_projection(
        store,
        "Compare",
        f"SELECT *, 'equal' AS status FROM {store.relation(units['id'])} WHERE detail='a'",
        units,
    )
    rejected = classification.save_projection(
        store,
        "StudyRelevance",
        f"SELECT *, 'unrelated_exam' AS reason FROM {store.relation(units['id'])}",
        units,
        port="issues",
    )
    runtime = SimpleNamespace(
        store=store,
        output_ids=[],
        outputs={
            "Checks": {"valid": units},
            "Compare": {"data": results},
            "StudyRelevance": {"issues": rejected},
        },
    )
    contract = {
        "sources": [{"node": "Settlements", "identity": "Checks"}],
        "checks": [
            {
                "name": "quantity",
                "units": {"node": "Checks", "port": "valid"},
                "results": [
                    {"node": "Compare", "port": "data", "status_field": "status"},
                    {
                        "node": "StudyRelevance",
                        "port": "issues",
                        "status": "uncompared",
                        "reason_field": "reason",
                        "fallback": True,
                    },
                ],
            }
        ],
    }
    assessment = audit(runtime, contract, [store.get(source["id"])])
    assert assessment["state"] == "accounted"
    assert assessment["coverage_gap_records"] == 0
    assert assessment["checks"][0]["counts"] == {"equal": 1, "uncompared": 1}
    records = store.page(assessment["checks"][0]["dataset_id"])["rows"]
    assert {row["unit_row_id"]: row["status"] for row in records} == {0: "equal", 1: "uncompared"}


def test_explicit_technique_modality_conflict_cannot_pass_rules():
    cfg, row = config(), record("BQ20ZUZZZ")
    row["study_chk_modality"] = "DR"
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist([row]))
        result = (
            db.execute(classification.rule_query(cfg, f"({code_dictionary.query(cfg, 'source')})"))
            .to_arrow_table()
            .to_pylist()[0]
        )
    assert result["study_relevance"] == "无法确定"
    assert result["_classification_conflict"] is True
