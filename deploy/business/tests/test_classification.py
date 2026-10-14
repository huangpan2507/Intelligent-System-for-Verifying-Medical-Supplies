# ruff: noqa: INP001, RUF001, S101, PLR2004 - synthetic Chinese fixtures and test assertions.
"""Classification boundaries: evidence, source facts, uncertainty and expression safety."""

import duckdb
import pyarrow as pa
import pytest
from langflow.business.expressions import expression
from langflow.business.relational import unary_query

from scripts.business.core_classification import model_configs, rule_configs


def transform(rows, configs):
    table = pa.Table.from_pylist([{**row, "_business_row_id": i} for i, row in enumerate(rows)])
    with duckdb.connect() as db:
        for config in configs:
            db.register("input_rows", table)
            query = unary_query("transform", config, "input_rows", table.column_names)["data"]
            table = db.execute(query).to_arrow_table()
            db.unregister("input_rows")
    return table.to_pylist()


def record(product, surgery="人工全髋关节置换术"):
    return {
        "HILIST_NAME": surgery,
        "PRODNAME": product,
        "HOS_PROJ_NAME": product,
        "MEDINS_LIST_NAME": product,
        "SPEC": "模拟规格一套",
        "CNT": 2,
        "PRIC": 10000,
    }


def test_rules_use_material_facts_not_surgery_and_keep_quantities():
    rows = [
        record("人工髋关节（模拟）"),
        record("非关节耗材（模拟对照项）"),
        record(None),
        record("膝关节假体系统（模拟）", "人工全膝关节置换术"),
        record("人工膝关节（模拟）"),
    ]
    result = transform(rows, rule_configs()[:2])
    assert [r["rule_category"] for r in result] == ["人工髋关节", "其他", "无法确定", "无法确定", "无法确定"]
    assert result[-1]["rule_conflict"]
    assert all(r["CNT"] == 2 and r["PRIC"] == 10000 for r in result)
    assert result[0]["rule_evidence_field"] == "PRODNAME"
    assert result[0]["rule_evidence_text"] == rows[0]["PRODNAME"]


def test_other_material_conflicting_with_joint_facts_cannot_auto_pass():
    row = {**record("非关节耗材（模拟对照项）"), "HOS_PROJ_NAME": "人工髋关节（模拟A型号）"}
    result = transform([row], rule_configs()[:2])[0]
    assert result["rule_conflict"]
    assert result["rule_category"] == "无法确定"
    assert result["rule_evidence_field"] == result["rule_evidence_text"] == ""


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ({}, "人工膝关节"),
        ({"model_confidence": 0.05}, "人工膝关节"),  # display score, no hidden threshold
        ({"model_evidence_field": "PRODNAME,HOS_PROJ_NAME"}, "无法确定"),
        ({"model_evidence_field": "HILIST_NAME", "model_evidence_text": "人工全膝关节置换术"}, "无法确定"),
        ({"model_evidence_text": "不存在的商品名"}, "无法确定"),
        ({"model_evidence_text": "   "}, "无法确定"),
        ({"model_reason": ""}, "无法确定"),
        ({"model_confidence": 1.5}, "无法确定"),
        ({"model_category": "无法确定"}, "无法确定"),
        ({"model_category": "其他", "model_reason": "明确非目标对照结论"}, "其他"),
        ({"rule_conflict": True}, "无法确定"),
        ({"model_category": "人工髋关节"}, "无法确定"),
    ],
)
def test_model_requires_real_material_quote_and_keeps_confidence_advisory(changed, expected):
    row = {
        **record("膝关节假体系统（模拟）", "人工全膝关节置换术"),
        "rule_conflict": False,
        "model_category": "人工膝关节",
        "model_reason": "具体耗材描述是膝关节假体系统",
        "model_evidence_field": "PRODNAME",
        "model_evidence_text": "膝关节假体系统",
        "model_confidence": 0.95,
        **changed,
    }
    result = transform([row], model_configs("unused")[1:])[0]
    assert result["target_category"] == expected
    assert result["classification_method"] == "model"
    assert result["CNT"] == 2
    assert result["PRIC"] == 10000
    if row["model_confidence"] == 1.5:
        assert result["classification_confidence"] is None


@pytest.mark.parametrize("value", ["__import__('os')", "x.__class__", "x[0]", "lambda: 1", "x in [1]", "x is None"])
def test_new_conditionals_do_not_allow_python_execution(value):
    with pytest.raises(ValueError, match="Expression supports"):
        expression(value, ["x"])


def test_conditional_sql_escapes_source_like_literals_and_handles_nulls():
    compiled = expression(
        "'hip' if contains(coalesce(name, ''), \"x'); DROP TABLE names; --\") else 'unknown'", ["name"]
    )
    with duckdb.connect() as db:
        query = f"SELECT {compiled} FROM (SELECT NULL::VARCHAR AS name)"  # noqa: S608 - testing the safe SQL compiler
        assert db.execute(query).fetchone() == ("unknown",)
