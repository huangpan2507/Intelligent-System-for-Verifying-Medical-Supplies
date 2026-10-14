"""Two-port validation: duplicate notices preserve accounting without blocking it."""
# ruff: noqa: S101, INP001, F811, PLR2004 - standalone business regression suite.

import copy
from decimal import Decimal

import httpx
import pytest
from langflow.business.components import from_langflow, to_langflow
from langflow.business.coverage import finalize
from langflow.business.sources import file_path
from langflow.business.templates import edge, node
from langflow.business.validate_migration import LEGACY_CODE, migrate_canvas, migrate_graph
from langflow.verification.api import create_app
from test_workflows import OWNER, env, execute_release, file_graph, save_release, upstream  # noqa: F401


@pytest.mark.parametrize("with_errors", [False, True])
async def test_duplicate_notices_do_not_double_count_block_or_inflate_unresolved(env, with_errors):
    graph = file_graph(env)
    source = graph["nodes"][0]
    rows = "code,value,extra\nA,10,D1\nA,10,D1\nB,20,D4\n"
    if with_errors:
        rows += "A,-5,D2\nA,-5,D2\nA,2,D3\nA,3,D3\n"
    file_path(OWNER, source["config"]["file_id"]).write_text(rows)
    graph["nodes"] = [
        source,
        node(
            "Checks",
            "validate",
            {
                "identity": {"name": "detail", "namespace": "test", "keys": ["extra"]},
                "conditions": [{"field": "value", "op": "ge", "value": 0}],
            },
        ),
        node(
            "Totals",
            "aggregate",
            {
                "group_by": ["code"],
                "metrics": [{"operation": "sum", "field": "value", "output": "total"}],
            },
        ),
        node("Compare", "compare", {"comparisons": [{"left": "total", "right": "total"}]}),
        node(
            "Result",
            "output",
            {
                "name": "result",
                "primary": True,
                "obligation": {
                    "mode": "verification",
                    "sources": [{"node": "Source", "identity": "Checks"}],
                    "checks": [
                        {
                            "name": "total",
                            "units": {"node": "Totals", "port": "data"},
                            "results": [{"node": "Compare", "port": "data", "status_field": "_comparison_status"}],
                        }
                    ],
                },
            },
        ),
    ]
    graph["edges"] = [
        edge("Source", "Checks"),
        edge("Checks", "Totals", "valid"),
        edge("Totals", "Compare"),
        edge("Compare", "Result"),
    ]
    runtime = await execute_release(env, save_release(env, graph))
    assert not runtime.failures
    assert set(runtime.outputs["Checks"]) == {"valid", "issues"}
    issues = runtime.outputs["Checks"]["issues"]
    issue_rows = runtime.store.page(issues["id"])["rows"]
    notices = [r for r in issue_rows if r["_issue_severity"] == "info"]
    assert len(notices) == 1
    assert notices[0]["extra"] == "D1"
    errors = [r for r in issue_rows if r["_issue_severity"] == "error"]
    assert len(errors) == (4 if with_errors else 0)
    if with_errors:
        assert {r["extra"] for r in errors} == {"D2", "D3"}
        assert any(r["_identity_status"] == "exact_duplicate" for r in errors)
    result = runtime.store.page(runtime.outputs["Result"]["data"]["id"])["rows"]
    assert {r["code"]: Decimal(r["total"]) for r in result} == {"A": 10, "B": 20}
    assert {r["code"]: r["_comparison_status"] for r in result} == {
        "A": "unknown" if with_errors else "equal",
        "B": "equal",
    }
    summary = finalize(runtime)
    assert summary["received_records"] == (7 if with_errors else 3)
    assert summary["business_identities"] == (4 if with_errors else 2)
    assert summary["missing_identity_records"] == 0
    assert summary["coverage_gap_records"] == (4 if with_errors else 0)
    db, settings = env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        response = await http.get(
            f"/api/v1/business/tasks/{runtime.task.id}", headers={"Authorization": "Bearer " + "a" * 20}
        )
    assert response.status_code == 200, response.text
    assert response.json()["unresolved_rows"] == len(errors)


def test_legacy_canvas_migration_preserves_error_and_duplicate_consumers(env):
    graph = file_graph(env)
    graph["nodes"].insert(
        1,
        node(
            "Checks",
            "validate",
            {
                "identity": {"name": "detail", "namespace": "test", "keys": ["code"]},
            },
        ),
    )
    graph["nodes"].append(node("Notices", "output", {"name": "duplicates"}))
    graph["edges"] = [edge("Source", "Checks"), edge("Checks", "Result", "issues"), edge("Checks", "Notices", "issues")]
    canvas = to_langflow(graph)
    checks = next(n for n in canvas["nodes"] if n["id"] == "Checks")
    checks["data"]["node"]["template"]["code"]["value"] = LEGACY_CODE
    old_edge = next(e for e in canvas["edges"] if e["target"] == "Notices")
    old_edge["data"]["sourceHandle"]["name"] = "duplicates"
    original = copy.deepcopy(canvas)
    updated = migrate_canvas(canvas)
    assert canvas == original
    assert migrate_canvas(updated) == updated
    compiled = from_langflow(updated)
    filter_node = next(n for n in compiled["nodes"] if n["kind"] == "filter")
    assert filter_node["config"]["conditions"] == [{"field": "_issue_severity", "op": "eq", "value": "info"}]
    assert {e["target"]: e["port"] for e in compiled["edges"] if e["source"] == filter_node["id"]} == {
        "Result": "unmatched",
        "Notices": "matched",
    }
    assert len(next(n for n in updated["nodes"] if n["id"] == "Checks")["data"]["node"]["outputs"]) == 2
    # Unrecognized component edits still fail publication, even on a legacy Validate.
    checks["data"]["node"]["template"]["code"]["value"] += "\nextra = 1\n"
    with pytest.raises(ValueError, match="Modified component code"):
        from_langflow(canvas)


def test_legacy_obligation_references_are_migrated_without_a_visible_wire():
    graph = {
        "nodes": [
            node("Checks", "validate", {}),
            node(
                "Result",
                "output",
                {
                    "obligation": {
                        "checks": [
                            {
                                "units": {"node": "Checks", "port": "valid"},
                                "results": [{"node": "Checks", "port": "issues"}],
                            }
                        ],
                        "dispositions": [{"node": "Checks", "port": "duplicates"}],
                    },
                },
            ),
        ],
        "edges": [],
    }
    updated = migrate_graph(graph)
    obligation = updated["nodes"][1]["config"]["obligation"]
    assert obligation["checks"][0]["units"] == {"node": "Checks", "port": "valid"}
    assert obligation["checks"][0]["results"][0]["port"] == "unmatched"
    assert obligation["dispositions"][0]["port"] == "matched"


async def test_new_consumable_template_does_not_report_duplicate_images_as_conflicts(env, upstream):
    from langflow.business.templates import consumables

    graph = consumables(upstream.id)
    for link in graph["edges"]:
        if link["source"] == "Images" and link["target"] == "ImageContext":
            link["source"] = "ImageCopies"
    graph["nodes"].extend([node("ImageCopy", "transform", {}), node("ImageCopies", "union", {})])
    graph["edges"].extend(
        [
            edge("Images", "ImageCopy"),
            edge("Images", "ImageCopies"),
            edge("ImageCopy", "ImageCopies"),
        ]
    )
    runtime = await execute_release(env, save_release(env, graph))
    assert not runtime.failures
    issues = runtime.store.page(runtime.outputs["ImageIdentities"]["issues"]["id"])["rows"]
    assert issues
    assert all(row["_issue_severity"] == "info" for row in issues)
    assert runtime.outputs["ImageIdentitiesIssues"]["data"]["row_count"] == 0
    summary = finalize(runtime)
    assert summary["coverage_gap_records"] == 0
    for check in summary["checks"]:
        assert check["counts"].get("result_conflict", 0) == 0


async def test_republish_legacy_release_keeps_error_and_duplicate_branches_separate(env):
    from langflow.business.models import Release
    from langflow.verification.database import fingerprint

    graph = file_graph(env)
    file_path(OWNER, graph["nodes"][0]["config"]["file_id"]).write_text(
        "code,value,extra\nA,1,x\nA,1,x\nB,2,y\nB,3,y\n"
    )
    graph["nodes"].extend(
        [
            node("Checks", "validate", {"identity": {"name": "detail", "namespace": "test", "keys": ["code"]}}),
            node("Notices", "output", {"name": "duplicate appearances"}),
        ]
    )
    graph["edges"] = [edge("Source", "Checks"), edge("Checks", "Result", "issues"), edge("Checks", "Notices", "issues")]
    release = save_release(env, graph)
    db, settings = env
    original = copy.deepcopy(release.package)
    original.pop("validate_issues_version")
    next(e for e in original["graph"]["edges"] if e["target"] == "Notices")["port"] = "duplicates"
    with db.sessions.begin() as session:
        row = session.get(Release, release.id)
        row.package = original
        row.content_hash = fingerprint(original)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        response = await http.post(
            f"/api/v1/business/internal/schemes/test/releases/from/{release.id}",
            headers={
                "Authorization": "Bearer " + settings.internal_token.get_secret_value(),
                "X-Business-Actor": OWNER,
            },
            json={"expected_revision": 0},
        )
    assert response.status_code == 201, response.text
    with db.sessions() as session:
        assert session.get(Release, release.id).package == original
        updated = session.get(Release, response.json()["id"])
    runtime = await execute_release(env, updated)
    assert not runtime.failures
    errors = runtime.store.page(runtime.outputs["Result"]["data"]["id"])["rows"]
    notices = runtime.store.page(runtime.outputs["Notices"]["data"]["id"])["rows"]
    assert [r["code"] for r in errors] == ["B", "B"]
    assert [r["code"] for r in notices] == ["A"]
