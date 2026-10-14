"""Regressions for native canvas node IDs and business schema inspection."""

import pytest
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow, to_langflow
from langflow.business.contracts import Node
from pydantic import ValidationError
from test_workflows import OWNER, env  # noqa: F401 - shared integration fixture


def test_inspect_native_database_nodes_preserves_canvas_ids(env):
    database, settings = env
    ids = [f"ext:business:BusinessDatabase@extra-{suffix}" for suffix in ["IrZ1y", "khLVH"]]
    canvas = to_langflow({"nodes": [{"id": node_id, "kind": "database"} for node_id in ids], "edges": []})

    result = inspect_graph(from_langflow(canvas), database, settings, OWNER, strict=False)

    # Incomplete nodes should report their own configuration error, not reject
    # the entire canvas because the native editor generated namespaced IDs.
    assert set(result["schemas"]) == set(ids)
    for node_id in ids:
        assert "'connection' is a required property" in result["errors"][node_id]


@pytest.mark.parametrize("node_id", ["Database-A", "ext:business:BusinessDatabase@extra-IrZ1y"])
def test_accept_canvas_node_id(node_id):
    assert Node(id=node_id, kind="database").id == node_id


@pytest.mark.parametrize("node_id", ["", "../Database", "Database/child", 'Database"', "Database A", "A" * 102])
def test_reject_invalid_node_id(node_id):
    with pytest.raises(ValidationError):
        Node(id=node_id, kind="database")


def test_lookup_rejects_unreviewed_source_change_before_reading_database(env):
    database, settings = env
    config = {
        "connection": "changed", "schema": "public", "table": "records",
        "binding_source": {"connection": "original", "schema": "public", "table": "records"},
        "keys": [{"left": "id", "right": "id"}],
        "returns": [{"field": "id", "output": "source_id"}],
    }
    graph = {"nodes": [{"id": "Lookup", "kind": "databaselookup", "config": config}], "edges": []}
    result = inspect_graph(graph, database, settings, OWNER, strict=False)
    assert "review field bindings" in result["errors"]["Lookup"]
