"""Generate an importable graph using the actual installed Langflow component ports."""

import json
from pathlib import Path

from lfx.extension.loader import discover_inline_bundles
from lfx.graph import Graph

ROOT = Path(__file__).resolve().parents[2]


def build_graph():
    results = discover_inline_bundles([ROOT / "deploy/verification/components"])
    result = next(result for result in results if result.bundle == "verification")
    if result.errors:
        raise RuntimeError(str(result.errors))
    classes = {item.class_name: item.klass for item in result.components}
    entry = classes["VerificationTaskInput"](_id="VerificationTaskInput-Verification")
    stages = sorted(
        (cls for name, cls in classes.items() if name != "VerificationTaskInput"),
        key=lambda cls: cls.stage,
    )
    previous = entry.message_response
    for cls in stages:
        component = cls(_id=f"{cls.__name__}-{cls.stage}")
        component.set(context=previous)
        previous = component.execute_stage
    return Graph(start=entry, end=component)


def build_payload():
    graph = build_graph()
    payload = graph.dump(
        name="高值耗材核验(模拟联调)",
        endpoint_name="consumable-verification",
        description="00—08核验流程。模拟服务不代表真实影像识别效果。",
    )
    nodes = payload["data"]["nodes"]
    entry_id = "VerificationTaskInput-Verification"
    ordered_ids = [entry_id, *sorted((n["id"] for n in nodes if n["id"] != entry_id), key=lambda name: name[-2:])]
    payload["data"]["nodes"].sort(key=lambda node: ordered_ids.index(node["id"]))
    for index, node in enumerate(payload["data"]["nodes"]):
        node["type"] = "genericNode"
        node["position"] = {"x": index * 360, "y": 100}
        node["data"]["type"] = f"ext:verification:{node['data']['type']}@extra"
    # Graph.dump supplies execution data; ReactFlow additionally needs renderer types and handle IDs.
    for edge in payload["data"]["edges"]:
        edge["id"] = f"verification-{edge['source']}-{edge['target']}"
        source_handle = edge["data"]["sourceHandle"]
        source_handle["dataType"] = f"ext:verification:{source_handle['dataType']}@extra"
        for name in ("sourceHandle", "targetHandle"):
            edge[name] = json.dumps(edge["data"][name], sort_keys=True, separators=(",", ":")).replace('"', "œ")
    return payload


if __name__ == "__main__":
    payload = build_payload()
    target = ROOT / "deploy/verification/consumable-verification-palette.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
