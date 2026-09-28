"""Generate an importable graph using the actual installed Langflow component ports."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from lfx.components.input_output import ChatInput
from lfx.extension.loader import discover_inline_bundles
from lfx.graph import Graph

ROOT = Path(__file__).resolve().parents[2]
STAGE_NAMES = [
    "00 任务入口校验",
    "01 结算快照",
    "02 耗材筛选",
    "03 检查关联",
    "04 部位初筛",
    "05 影像清单",
    "06 模型识别",
    "07 确定性比较",
    "08 结果保存",
]


def build_graph():
    path = ROOT / "deploy/verification/components/verification/stage.py"
    spec = importlib.util.spec_from_file_location("verification_stage", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    entry = ChatInput(_id="ChatInput-Verification")
    entry.set(should_store_message=False)
    previous = entry.message_response
    stages = []
    for index, label in enumerate(STAGE_NAMES):
        component = module.ConsumableVerificationStage(_id=f"ConsumableVerificationStage-{index:02d}")
        component.set(stage=f"{index:02d}", context=previous)
        component.display_name = label
        component.description = component.STAGE_DESCRIPTIONS[f"{index:02d}"]
        stages.append(component)
        previous = component.execute_stage
    return Graph(start=entry, end=stages[-1])


def build_palette_graph():
    results = discover_inline_bundles([ROOT / "deploy/verification/components"])
    result = next(result for result in results if result.bundle == "verification")
    if result.errors:
        raise RuntimeError(str(result.errors))
    classes = {item.class_name: item.klass for item in result.components}
    entry = classes["VerificationTaskInput"](_id="VerificationTaskInput-Verification")
    stages = sorted(
        (cls for name, cls in classes.items() if name not in {"VerificationTaskInput", "ConsumableVerificationStage"}),
        key=lambda cls: cls.stage,
    )
    previous = entry.message_response
    for cls in stages:
        component = cls(_id=f"{cls.__name__}-{cls.stage}")
        component.set(context=previous)
        previous = component.execute_stage
    return Graph(start=entry, end=component)


def build_payload(*, palette=False):
    graph = build_palette_graph() if palette else build_graph()
    payload = graph.dump(
        name="高值耗材核验(模拟联调)",
        endpoint_name="consumable-verification",
        description="01—08核验流程。模拟服务不代表真实影像识别效果。",
    )
    if palette:
        nodes = payload["data"]["nodes"]
        entry_id = "VerificationTaskInput-Verification"
        ordered_ids = [entry_id, *sorted((n["id"] for n in nodes if n["id"] != entry_id), key=lambda name: name[-2:])]
    else:
        ordered_ids = ["ChatInput-Verification", *[f"ConsumableVerificationStage-{i:02d}" for i in range(9)]]
    payload["data"]["nodes"].sort(key=lambda node: ordered_ids.index(node["id"]))
    for index, node in enumerate(payload["data"]["nodes"]):
        node["type"] = "genericNode"
        node["position"] = {"x": index * 360, "y": 100}
        if palette:
            node["data"]["type"] = f"ext:verification:{node['data']['type']}@extra"
        if node["id"].startswith("ConsumableVerificationStage-"):
            component = sys.modules["verification_stage"].ConsumableVerificationStage()
            template = node["data"]["node"]["template"]
            node["data"]["node"]["template"] = component.update_build_config(template, node["id"][-2:], "stage")
            node["data"]["node"]["description"] = component.STAGE_DESCRIPTIONS[node["id"][-2:]]
    # Graph.dump supplies execution data; ReactFlow additionally needs renderer types and handle IDs.
    for edge in payload["data"]["edges"]:
        edge["id"] = f"verification-{edge['source']}-{edge['target']}"
        if palette:
            source_handle = edge["data"]["sourceHandle"]
            source_handle["dataType"] = f"ext:verification:{source_handle['dataType']}@extra"
        for name in ("sourceHandle", "targetHandle"):
            edge[name] = json.dumps(edge["data"][name], sort_keys=True, separators=(",", ":")).replace('"', "œ")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--palette", action="store_true", help="Export the individually draggable Verification components"
    )
    args = parser.parse_args()
    payload = build_payload(palette=args.palette)
    filename = "consumable-verification-palette.json" if args.palette else "consumable-verification.json"
    target = ROOT / "deploy/verification" / filename
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
