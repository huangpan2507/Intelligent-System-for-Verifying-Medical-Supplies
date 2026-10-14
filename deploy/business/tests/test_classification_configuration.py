# ruff: noqa: INP001, S101, F811, PLR2004, RUF001, PT018 - synthetic fixtures and business labels.
"""Classification field roles, matching and the single two-port contract."""

import json
from types import SimpleNamespace
from uuid import uuid4

import duckdb
import httpx
import jsonschema
import pyarrow as pa
import pytest
from langflow.business import classification
from langflow.business.catalog import CATALOG
from langflow.business.classification_config import effective_config, model_prompt, system_message
from langflow.business.components import from_langflow, to_langflow
from langflow.business.coverage import finalize
from langflow.business.models import Connection
from langflow.business.sources import file_path
from langflow.business.templates import edge, node
from langflow.verification.api import create_app
from test_compact_core import config, material
from test_workflows import OWNER, env, execute_release, file_graph, save_release  # noqa: F401


def rule_rows(cfg, rows):
    with duckdb.connect() as db:
        db.register("source", pa.Table.from_pylist(rows))
        return db.execute(classification.rule_query(cfg, "source")).fetch_arrow_table().to_pylist()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("人工全髋关节", "人工髋关节"),
        ("髋关节用人工材料", "人工髋关节"),
        ("人工髋部支具与膝关节配件", "无法确定"),
        ("髋关节表面置换术", "无法确定"),
        ("未使用人工全髋关节", "无法确定"),
        ("人工髋关节取出器", "无法确定"),
    ],
)
def test_all_keywords_and_ambiguity(text, expected):
    result = rule_rows(config("Classification"), [material(text, "人工全髋关节置换术")])[0]
    assert result["target_category"] == expected
    assert result["CNT"] == 1 and result["PRIC"] == 5000
    assert result["_classification_conflict"] == ("膝关节配件" in text)
    if "未使用" in text or "取出器" in text:
        hints = json.loads(result["classification_ambiguity"])
        assert hints[0]["original"] == text


def test_no_cross_field_matching_and_all_hits_checked_for_ambiguity():
    cfg = config("Classification")
    row = material("人工", "髋部手术")
    row.update(HOS_PROJ_NAME="髋关节", MEDINS_LIST_NAME="材料")
    assert rule_rows(cfg, [row])[0]["target_category"] == "无法确定"
    row.update(PRODNAME="人工全髋关节", HOS_PROJ_NAME="人工髋关节取出器")
    result = rule_rows(cfg, [row])[0]
    assert result["target_category"] == "无法确定"
    assert json.loads(result["classification_ambiguity"])[0]["field"] == "HOS_PROJ_NAME"


def test_contains_and_all_keywords_have_distinct_semantics_and_custom_fields_stay_explicit():
    cfg = config("Classification")
    cfg["rules"] = [{"fields": ["PRODNAME"], "op": "contains", "value": "人工髋关节", "category": "人工髋关节"}]
    assert rule_rows(cfg, [material("人工全髋关节", "髋")])[0]["target_category"] == "无法确定"
    assert rule_rows(cfg, [material("人工髋关节取出器", "髋")])[0]["target_category"] == "无法确定"
    row = material("材料", "髋")
    row["HOS_PROJ_NAME"] = "人工髋关节"
    assert rule_rows(cfg, [row])[0]["target_category"] == "无法确定"
    cfg["rules"][0].pop("fields")
    assert rule_rows(cfg, [row])[0]["target_category"] == "人工髋关节"


@pytest.mark.parametrize("keywords", [[], [""], ["人工", " "]])
def test_empty_keywords_fail_publication(keywords):
    cfg = config("Classification")
    cfg["rules"][0]["keywords"] = keywords
    with pytest.raises(ValueError, match="nonempty keywords"):
        classification.validate_config(cfg, effective_config(cfg)["input_fields"])


def test_prompts_follow_roles_and_categories():
    cfg = config("Classification")
    cfg["category_routes"][0]["category"] = "Renamed"
    cfg["classification_fields"][1]["role"] = "context"
    text = model_prompt(cfg)
    assert '"Renamed"' in text
    contract = json.loads(text.split("\nBusiness guidance:\n")[0].split("\n", 1)[1])
    assert "PRODNAME" not in contract["evidence_fields"] and "PRODNAME" in contract["context_fields"]


@pytest.mark.parametrize(
    "key",
    [
        "input_fields",
        "evidence_fields",
        "categories",
        "target_categories",
        "prompt",
        "legacy_prompt",
        "unknown_category",
    ],
)
def test_obsolete_configuration_fields_are_rejected(key):
    cfg = config("Classification")
    cfg[key] = "obsolete"
    with pytest.raises(jsonschema.ValidationError, match="Additional properties"):
        jsonschema.validate(cfg, CATALOG["classification"]["schema"])


def test_invalid_custom_reference_is_rejected_not_dropped():
    cfg = config("Classification")
    cfg["rules"][0]["fields"] = ["PRODNAME"]
    cfg["classification_fields"][1]["role"] = "context"
    with pytest.raises(ValueError, match="evidence fields"):
        classification.validate_config(cfg, effective_config(cfg)["input_fields"])
    assert cfg["rules"][0]["fields"] == ["PRODNAME"]


def test_canvas_roundtrip_keeps_only_two_ports_without_adding_nodes():
    graph = {
        "nodes": [
            node("C", "classification", config("Classification")),
            node("R", "output", {"name": "result"}),
        ],
        "edges": [edge("C", "R")],
    }
    canvas = to_langflow(graph)
    classification_node = next(n for n in canvas["nodes"] if n["id"] == "C")
    assert {p["name"] for p in classification_node["data"]["node"]["outputs"]} == {"data", "issues"}
    restored = from_langflow(canvas)
    assert len(restored["nodes"]) == 2 and restored["edges"] == graph["edges"]
    assert restored["nodes"][0]["config"] == graph["nodes"][0]["config"]
    template = classification_node["data"]["node"]["template"]
    template["code"]["value"] = template["code"]["value"].replace('name="issues"', 'name="excluded"')
    with pytest.raises(ValueError, match="Modified component code"):
        from_langflow(canvas)


async def test_data_only_connection_persists_nonempty_issues_and_counts_by_row(env, monkeypatch):
    db, settings = env
    graph = file_graph(env)
    source = graph["nodes"][0]
    file_path(OWNER, source["config"]["file_id"]).write_text(
        "code,value,extra\n目标,10,A\n非关节耗材（模拟对照项）,20,B\n未知,30,C\n"
    )
    connection_id = str(uuid4())
    with db.sessions.begin() as session:
        session.add(
            Connection(
                id=connection_id,
                owner_id=OWNER,
                name="fixture",
                kind="model",
                config={"base_url": "https://fixture.invalid"},
            )
        )
    cfg = {
        "classification_fields": [{"field": "code", "role": "evidence"}],
        "category_routes": [{"category": "target", "continue": True}, {"category": "other", "continue": False}],
        "business_guidance": "Fixture",
        "connection": connection_id,
        "path": "/chat",
        "model": "fixture",
        "rules": [
            {"op": "eq", "value": "目标", "category": "target"},
            {"op": "eq", "value": "非关节耗材（模拟对照项）", "category": "other"},
        ],
    }
    monkeypatch.setattr(
        "langflow.business.sources.client_for",
        lambda *_: httpx.Client(
            base_url="https://fixture.invalid",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
            ),
        ),
    )
    graph["nodes"] = [
        source,
        node("V", "validate", {"identity": {"name": "detail", "namespace": "fixture", "keys": ["extra"]}}),
        node("C", "classification", cfg),
        node("Compare", "compare", {"comparisons": [{"left": "value", "right": "value"}]}),
        node(
            "Result",
            "output",
            {
                "name": "result",
                "primary": True,
                "obligation": {
                    "mode": "verification",
                    "sources": [{"node": "Source", "identity": "V"}],
                    "checks": [
                        {
                            "name": "value",
                            "units": {"node": "C", "port": "data"},
                            "results": [{"node": "Compare", "port": "data", "status_field": "_comparison_status"}],
                        }
                    ],
                    "dispositions": [
                        {
                            "node": "C",
                            "port": "issues",
                            "status_field": "classification_disposition",
                            "reason_field": "classification_disposition_reason",
                        }
                    ],
                },
            },
        ),
    ]
    graph["edges"] = [edge("Source", "V"), edge("V", "C", "valid"), edge("C", "Compare"), edge("Compare", "Result")]
    runtime = await execute_release(env, save_release(env, graph))
    assert not runtime.failures
    assert set(runtime.outputs["C"]) == {"data", "issues"}
    assert runtime.outputs["C"]["data"]["row_count"] == 1
    issues = runtime.outputs["C"]["issues"]
    assert issues["row_count"] == 2
    assert {r["classification_disposition"] for r in runtime.store.page(issues["id"])["rows"]} == {
        "excluded",
        "uncompared",
    }
    summary = finalize(runtime)
    assert summary["state"] == "accounted" and summary["coverage_gap_records"] == 0
    dispositions = runtime.store.page(summary["dispositions_dataset_id"])["rows"]
    assert {r["status"] for r in dispositions} == {"equal", "excluded", "uncompared"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        response = await http.get(
            f"/api/v1/business/tasks/{runtime.task.id}", headers={"Authorization": "Bearer " + "a" * 20}
        )
    assert response.status_code == 200
    assert response.json()["unresolved_rows"] == 1  # No duplicate count from raw model issues.
    assert response.json()["classification_counts"] == {"continue": 1, "excluded": 1, "uncompared": 1}


@pytest.mark.parametrize("hard_conflict", [False, True])
def test_model_can_resolve_ambiguity_but_not_hard_conflicts(env, monkeypatch, hard_conflict):
    db, settings = env
    from langflow.business.datasets import DatasetStore

    store = DatasetStore(db, str(uuid4()))
    rows = [material("人工髋关节取出器", "膝关节手术" if hard_conflict else "髋关节手术")]
    source = store.write_batches("source", [rows], pa.Table.from_pylist(rows).schema)
    cfg = config("Classification")
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        answer = {
            "model_category": "其他",
            "model_reason": "原文描述取出器",
            "model_evidence_field": "PRODNAME",
            "model_evidence_text": "取出器",
            "model_confidence": 0.2,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    monkeypatch.setattr(
        "langflow.business.sources.client_for",
        lambda *_: httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(respond)),
    )
    runtime = SimpleNamespace(
        store=store, settings=settings, prefix="", connection=lambda _: SimpleNamespace(id=str(uuid4()))
    )
    outputs = classification.execute(runtime, {"id": "C", "config": cfg}, source)
    assert len(calls) == 1 and calls[0]["messages"][0]["content"] == system_message(cfg)
    row = store.page(outputs["issues"]["id"])["rows"][0]
    assert row["classification_disposition"] == ("uncompared" if hard_conflict else "excluded")
    assert json.loads(row["classification_ambiguity"])
