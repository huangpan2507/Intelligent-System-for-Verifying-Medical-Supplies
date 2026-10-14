"""Langflow graph components; configuration UI edits the same saved canvas fields."""

import ast
import contextvars
import json
from functools import lru_cache

from lfx.custom import Component
from lfx.io import DataInput, MultilineInput
from lfx.schema.data import Data

ACTIVE_RUNTIME = contextvars.ContextVar("business_runtime", default=None)


class BusinessComponent(Component):
    icon = "Workflow"
    kind = ""
    inputs = [
        DataInput(name="input_data", display_name="Data", is_list=True, required=False),
        DataInput(name="input_left", display_name="Left data", required=False),
        DataInput(name="input_right", display_name="Right data", required=False),
        MultilineInput(
            name="configuration",
            display_name="Configuration",
            value="{}",
            advanced=True,
            info="Edit fields visually with Business configuration in the canvas.",
        ),
    ]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from langflow.business.catalog import CATALOG

        specification = CATALOG.get(cls.kind)
        if specification is None:
            return
        # Retain legacy field names so saved edges/configuration survive a
        # component refresh. Only the capability's real inputs are exposed.
        cls.inputs = [field.model_copy(deep=True) for field in BusinessComponent.inputs]
        for field in cls.inputs:
            if cls.kind == "taskinput" and field.name == "configuration":
                field.show = False
            if not field.name.startswith("input_"):
                continue
            port = field.name.removeprefix("input_")
            field.show = port in specification["inputs"]
            field.is_list = bool(specification.get("multiple") and port == "data")
            field.required = field.show and port not in specification.get("optional_inputs", [])
            if cls.kind == "database" and port == "data":
                field.display_name = "Parameters"
                field.show = True
                field.required = False
                field.info = "Optional task parameter dependency; this source does not consume an upstream dataset."

    async def output_port(self, port):
        runtime = ACTIVE_RUNTIME.get()
        if runtime is None:
            msg = "Publish this business scheme and submit a task to execute with persistent datasets"
            raise ValueError(msg)
        refs = await runtime.execute(self._id)
        return Data(data=refs.get(port, {}))

    async def out_data(self) -> Data:
        return await self.output_port("data")

    async def out_valid(self) -> Data:
        return await self.output_port("valid")

    async def out_issues(self) -> Data:
        return await self.output_port("issues")

    async def out_excluded(self) -> Data:
        return await self.output_port("excluded")

    async def out_matched(self) -> Data:
        return await self.output_port("matched")

    async def out_unmatched(self) -> Data:
        return await self.output_port("unmatched")

    async def out_unknown(self) -> Data:
        return await self.output_port("unknown")

    async def out_members(self) -> Data:
        return await self.output_port("members")


def classes():
    return _classes()


@lru_cache(maxsize=1)
def _classes():
    from pathlib import Path

    from lfx.extension.loader import discover_inline_bundles

    root = next(p for p in Path(__file__).resolve().parents if (p / "deploy/verification/components/business").is_dir())
    bundle = next(
        b for b in discover_inline_bundles([root / "deploy/verification/components"]) if b.bundle == "business"
    )
    if bundle.errors:
        raise ValueError(str(bundle.errors))
    from langflow.business.catalog import PLUGINS

    return {
        **{c.klass.kind: c.klass for c in bundle.components},
        **{kind: plugin.component for kind, plugin in PLUGINS.items() if plugin.component},
    }


def to_langflow(spec, name="Business workflow"):
    from lfx.graph import Graph

    kinds = classes()
    components = {n["id"]: kinds[n["kind"]](_id=n["id"]) for n in spec["nodes"]}
    for node in spec["nodes"]:
        components[node["id"]].set(configuration=json.dumps(node.get("config", {}), ensure_ascii=False))
    graph = Graph()
    for component in components.values():
        graph.add_component(component)
    for edge in spec["edges"]:
        graph.add_component_edge(
            edge["source"], (edge.get("port", "data"), "input_" + edge.get("input", "data")), edge["target"]
        )
    graph.initialize()
    payload = graph.dump(name=name)
    by_id = {n["id"]: n for n in spec["nodes"]}
    for index, node in enumerate(payload["data"]["nodes"]):
        original = by_id[node["id"]]
        node["type"] = "genericNode"
        node["position"] = original.get("position") or {"x": (index % 5) * 350, "y": (index // 5) * 320}
        node["data"]["type"] = f"ext:business:Business{original['kind'].title()}@extra"
        node["data"]["node"]["display_name"] = original.get("label") or node["data"]["node"]["display_name"]
        node["data"]["node"]["template"]["_business_kind"] = {"value": original["kind"], "show": False}
    for index, edge in enumerate(payload["data"]["edges"]):
        edge["id"] = f"business-edge-{index}"
        sh = edge["data"]["sourceHandle"]
        sh["dataType"] = f"ext:business:{sh['dataType']}@extra"
        target = next(n for n in payload["data"]["nodes"] if n["id"] == edge["target"])
        th = edge["data"]["targetHandle"]
        field = target["data"]["node"]["template"][th["fieldName"]]
        # Graph.dump serializes FieldTypes.OTHER, while the canvas handle uses
        # the template's wire value "other". A mismatch deletes saved edges.
        th["type"] = field["type"]
        th["inputTypes"] = field.get("input_types", [])
        for key in ["sourceHandle", "targetHandle"]:
            edge[key] = json.dumps(edge["data"][key], sort_keys=True, separators=(",", ":")).replace('"', "œ")
    payload["data"]["viewport"] = {"x": 180, "y": 200, "zoom": 0.35}
    return payload["data"]


def from_langflow(graph):
    from langflow.business.catalog import CATALOG
    from langflow.business.validate_migration import is_legacy_validate, migrate_graph

    nodes = []
    legacy_validate = set()
    for node in graph.get("nodes", []):
        template = node["data"]["node"]["template"]
        kind = template.get("_business_kind", {}).get("value")
        if not kind:
            class_name = node["data"]["type"].split(":")[-1].split("@")[0]
            kind = class_name.removeprefix("Business").lower()
        if kind not in CATALOG:
            msg = f"Unsupported published business component: {kind}"
            raise ValueError(msg)
        saved_code = template.get("code", {}).get("value")
        registered_code = classes()[kind]().code
        if kind == "validate" and is_legacy_validate(saved_code):
            legacy_validate.add(node["id"])
        elif not saved_code or ast.dump(ast.parse(saved_code)) != ast.dump(ast.parse(registered_code)):
            msg = "Modified component code must be registered as a business capability before publication"
            raise ValueError(msg)
        nodes.append(
            {
                "id": node["id"],
                "kind": kind,
                "label": node["data"]["node"].get("display_name", kind),
                "config": json.loads(template.get("configuration", {}).get("value") or "{}"),
                "position": node.get("position", {}),
            }
        )
    edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "port": e.get("data", {}).get("sourceHandle", {}).get("name", "data"),
            "input": e.get("data", {}).get("targetHandle", {}).get("fieldName", "input_data").removeprefix("input_"),
        }
        for e in graph.get("edges", [])
    ]
    return migrate_graph({"nodes": nodes, "edges": edges}, legacy_validate)
