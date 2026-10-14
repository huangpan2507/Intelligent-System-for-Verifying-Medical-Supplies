"""Preserve old Validate consumers when merging duplicate notices into Issues."""

import ast
import copy
import hashlib
import json

ISSUES_VERSION = 2
LEGACY_CODE = """from langflow.business.components import BusinessComponent
from lfx.io import Output

class BusinessValidate(BusinessComponent):
    display_name = "Business Validate"
    description = "Persistent business datasets: validate"
    name = "BusinessValidate"
    kind = "validate"
    outputs = [
        Output(display_name="Valid", name="valid", method="out_valid", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
        Output(display_name="Duplicates", name="duplicates", method="out_duplicates", group_outputs=True),
    ]
"""


def is_legacy_validate(code):
    return bool(code) and ast.dump(ast.parse(code)) == ast.dump(ast.parse(LEGACY_CODE))


def migrate_graph(graph, legacy_ids=None):
    """Call only for known legacy canvases/releases, never guess a new graph's intent."""
    graph = copy.deepcopy(graph)
    validators = [n for n in graph["nodes"] if n["kind"] == "validate"]
    if legacy_ids is not None:
        validators = [n for n in validators if n["id"] in legacy_ids]
    references = []
    for node in graph["nodes"]:
        obligation = node.get("config", {}).get("obligation", {})
        references.extend(obligation.get("dispositions", []))
        for check in obligation.get("checks", []):
            references.extend([check["units"], *check["results"]])
    for node in validators:
        node_id = node["id"]
        edges = [e for e in graph["edges"] if e["source"] == node_id and e.get("port") in {"issues", "duplicates"}]
        refs = [r for r in references if r["node"] == node_id and r["port"] in {"issues", "duplicates"}]
        if not edges and not refs:
            continue
        if not node.get("config", {}).get("identity") and not any(
            item.get("port") == "duplicates" for item in [*edges, *refs]
        ):
            continue
        suffix = hashlib.sha256(node_id.encode()).hexdigest()[:12]
        filter_id = f"ValidateNotices_{suffix}"
        used = {n["id"] for n in graph["nodes"]}
        while filter_id in used:
            filter_id += "x"
        position = node.get("position", {})
        graph["nodes"].append(
            {
                "id": filter_id,
                "kind": "filter",
                "label": "Validation notices",
                "position": {"x": position.get("x", 0) + 350, "y": position.get("y", 0) + 200},
                "config": {"conditions": [{"field": "_issue_severity", "op": "eq", "value": "info"}]},
            }
        )
        for edge in edges:
            edge["source"] = filter_id
            edge["port"] = "matched" if edge["port"] == "duplicates" else "unmatched"
        for ref in refs:
            ref["node"] = filter_id
            ref["port"] = "matched" if ref["port"] == "duplicates" else "unmatched"
        graph["edges"].append({"source": node_id, "port": "issues", "target": filter_id, "input": "data"})
    return graph


def migrate_canvas(canvas):
    """Refresh only known old wrappers and affected edges/configuration; preserve layout."""
    from langflow.business.components import from_langflow, to_langflow

    legacy = {
        n["id"]
        for n in canvas.get("nodes", [])
        if is_legacy_validate(n.get("data", {}).get("node", {}).get("template", {}).get("code", {}).get("value"))
    }
    if not legacy:
        return copy.deepcopy(canvas)
    graph = from_langflow(canvas)
    fresh = to_langflow(graph)
    specs = {n["id"]: n for n in graph["nodes"]}
    replacements = {n["id"]: n for n in fresh["nodes"]}
    result = copy.deepcopy(canvas)
    for node in result["nodes"]:
        definition = node["data"]["node"]
        replacement = replacements[node["id"]]["data"]["node"]
        if node["id"] in legacy:
            definition["outputs"] = replacement["outputs"]
            definition["template"]["code"] = replacement["template"]["code"]
        config = specs[node["id"]]["config"]
        if json.loads(definition["template"]["configuration"]["value"] or "{}") != config:
            definition["template"]["configuration"]["value"] = json.dumps(config, ensure_ascii=False)
    old_ids = {n["id"] for n in result["nodes"]}
    result["nodes"].extend(n for n in fresh["nodes"] if n["id"] not in old_ids)
    # Graph.dump may reorder edges, so join by endpoints/ports, never list position.
    fresh_edges = {
        (
            e["source"],
            e["target"],
            e["data"]["sourceHandle"]["name"],
            e["data"]["targetHandle"]["fieldName"].removeprefix("input_"),
        ): e
        for e in fresh["edges"]
    }

    def replacement_edge(spec):
        return fresh_edges[(spec["source"], spec["target"], spec.get("port", "data"), spec.get("input", "data"))]

    for index, edge in enumerate(result["edges"]):
        replacement = replacement_edge(graph["edges"][index])
        if edge["source"] != replacement["source"]:
            edge["source"] = replacement["source"]
            edge["sourceHandle"] = replacement["sourceHandle"]
            edge["data"]["sourceHandle"] = replacement["data"]["sourceHandle"]
    used_edges = {e["id"] for e in result["edges"]}
    for spec in graph["edges"][len(result["edges"]) :]:
        edge = replacement_edge(spec)
        while edge["id"] in used_edges:
            edge["id"] += "x"
        used_edges.add(edge["id"])
        result["edges"].append(edge)
    return result
