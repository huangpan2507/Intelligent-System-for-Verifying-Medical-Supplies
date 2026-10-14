# ruff: noqa: S608 - queries use quoted identifiers and DatasetStore-owned relations.
"""Optional domain capabilities registered without changing generic relational execution."""

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points


@dataclass(frozen=True)
class NodePlugin:
    specification: dict
    output_fields: list[dict]
    execute: Callable
    component: type | None = None


def _imaging(runtime, node, inputs):
    from langflow.business.sources import model_read

    config = node["config"]
    body = {k.removesuffix("_field"): {"field": v} for k, v in config.items() if k.endswith("_field")}
    adapted = {
        "fields": plugins()["imaging"].output_fields,
        "input_fields": [v["field"] for v in body.values()],
        "body": body,
        "path": config["path"],
        "max_calls": config.get("max_calls", 1000),
    }
    result = model_read(
        runtime.store,
        runtime.prefix + node["id"],
        adapted,
        runtime.connection(config["connection"]),
        runtime.settings,
        inputs["data"][0],
        optional_output_fields={"observed_unit"},
    )
    if not config.get("result_checks"):
        return result
    from langflow.business.classification import save_projection
    from langflow.business.datasets import ident

    checked = runtime.run_node(
        {"id": node["id"] + "--result-checks", "kind": "validate", "config": config["result_checks"]},
        {"data": [result["data"]]},
    )
    columns = ", ".join(ident(f["name"]) for f in result["data"]["fields"])
    node_id = runtime.prefix + node["id"]
    source = inputs["data"][0]
    return {
        "data": save_projection(
            runtime.store,
            node_id,
            f"SELECT {columns} FROM {runtime.store.relation(checked['valid']['id'])}",
            source,
            parents=[checked["valid"]["id"]],
        ),
        "issues": save_projection(
            runtime.store,
            node_id,
            f"SELECT {columns} FROM {runtime.store.relation(result['issues']['id'])} UNION ALL "
            f"SELECT {columns} FROM {runtime.store.relation(checked['issues']['id'])}",
            source,
            port="issues",
            parents=[result["issues"]["id"], checked["issues"]["id"]],
        ),
    }


def plugins():
    from langflow.business.catalog import CHECKS, CONNECTION, FIELD, obj, string

    imaging = NodePlugin(
        specification={
            "ports": ["data", "issues"],
            "inputs": ["data"],
            "schema": obj(
                {
                    "connection": CONNECTION,
                    "path": string(),
                    "patient_field": FIELD,
                    "encounter_field": FIELD,
                    "category_field": FIELD,
                    "result_checks": CHECKS,
                    "hospital_field": FIELD,
                    "evidence_field": FIELD,
                    "evidence_context_field": FIELD,
                    "max_calls": {"type": "integer", "minimum": 1, "maximum": 100000},
                },
                [
                    "connection",
                    "path",
                    "patient_field",
                    "category_field",
                    "hospital_field",
                    "evidence_field",
                ],
            ),
        },
        output_fields=[
            {"name": "recognized_category", "type": "text"},
            {"name": "recognized_quantity", "type": "number"},
            {"name": "observed_unit", "type": "text"},
            {"name": "coverage_confirmed", "type": "boolean"},
            {"name": "evidence_ref", "type": "text"},
            {"name": "recognition_confirmed", "type": "boolean"},
            {"name": "simulated", "type": "boolean"},
        ],
        execute=_imaging,
    )
    registry = {"imaging": imaging}
    for entry in entry_points(group="langflow.business_nodes"):
        if entry.name in registry:
            msg = f"Duplicate business capability: {entry.name}"
            raise ValueError(msg)
        registry[entry.name] = entry.load()()
    return registry
