# ruff: noqa: S101, PLR2004, INP001 - numeric comparison regression examples.
"""Strict comparison, calculation order and retired configuration migration."""

import copy
import json
from decimal import Decimal

import duckdb
import jsonschema
import pytest
from langflow.business.catalog import CATALOG
from langflow.business.relational import unary_query

from scripts.business.apply_compare_configuration import clean_canvas


def test_rejects_retired_tolerance_even_when_zero():
    for tolerance in (0, 1, 0.01):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"comparisons": [{"left": "a", "right": "b", "mode": "numeric", "tolerance": tolerance}]},
                CATALOG["compare"]["schema"],
            )


@pytest.mark.parametrize(
    ("left", "right", "reason", "expected"),
    [
        ("1.00", "1", "", "equal"),
        ("1", "1.00000001", "", "different"),
        ("10000", "9999.99999999", "", "different"),
        (None, "1", "", "unknown"),
        (None, None, "", "unknown"),
        ("1", "1", "missing_evidence", "unknown"),
    ],
)
def test_numeric_equality_without_rounding(left, right, reason, expected):
    source = "(SELECT CAST(? AS DECIMAL(20,8)) AS a, CAST(? AS DECIMAL(20,8)) AS b, ? AS _issue_reason)"
    query = unary_query(
        "compare",
        {"comparisons": [{"left": "a", "right": "b", "mode": "numeric", "output": "status"}]},
        source,
        ["a", "b", "_issue_reason"],
    )["data"]
    with duckdb.connect() as db:
        cursor = db.execute(query, [left, right, reason])
        row = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    assert row["status"] == expected
    if left is not None and right is not None:
        assert row["difference_0"] == Decimal(right) - Decimal(left)


def test_calculations_feed_comparisons_and_retain_trace():
    config = {
        "calculations": [
            {"operation": "copy", "field": "row_id", "output": "unit_row_id"},
            {"operation": "expression", "expression": "qty * price", "output": "settled"},
            {"operation": "expression", "expression": "seen * price", "output": "observed"},
        ],
        "comparisons": [
            {"left": "category", "right": "recognized", "output": "category_status"},
            {"left": "qty", "right": "seen", "mode": "numeric"},
            {"left": "settled", "right": "observed", "mode": "numeric"},
        ],
    }
    query = unary_query(
        "compare",
        config,
        (
            "(SELECT 0 AS _business_row_id, 7 AS row_id, 2 AS qty, 1 AS seen, "
            "10000 AS price, 'hip' AS category, 'knee' AS recognized)"
        ),
        ["_business_row_id", "row_id", "qty", "seen", "price", "category", "recognized"],
    )["data"]
    with duckdb.connect() as db:
        cursor = db.execute(query)
        row = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    assert row["unit_row_id"] == 7
    assert (row["settled"], row["observed"], row["difference_1"], row["difference_2"]) == (20000, 10000, -1, -10000)
    assert row["category_status"] == row["_comparison_status"] == "different"


def test_migration_changes_only_compare_tolerance_and_reports_nonzero():
    config = {"comparisons": [{"left": "a", "right": "b", "tolerance": 0.5}], "calculations": []}
    canvas = {
        "nodes": [
            {
                "id": "Compare",
                "position": {"x": 1},
                "data": {
                    "type": "ext:business:BusinessCompare@1",
                    "node": {"template": {"configuration": {"value": json.dumps(config)}}},
                },
            }
        ],
        "edges": [{"source": "Compare", "target": "Output"}],
    }
    before = copy.deepcopy(canvas)
    removed = clean_canvas(canvas)
    assert removed == [{"node": "Compare", "comparison": 0, "previous_tolerance": 0.5}]
    expected = copy.deepcopy(before)
    config["comparisons"][0].pop("tolerance")
    expected["nodes"][0]["data"]["node"]["template"]["configuration"]["value"] = json.dumps(config, ensure_ascii=False)
    assert canvas == expected
    assert clean_canvas(canvas) == []
