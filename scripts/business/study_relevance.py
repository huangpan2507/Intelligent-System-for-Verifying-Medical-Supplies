# ruff: noqa: RUF001 - reviewed Chinese business configuration.
"""The confirmed eleven-node template and its reusable classification configuration."""

from copy import deepcopy

PREFIX = "study_relevance"


def classification_config(model):
    name = PREFIX + "_code_name"
    rules = []
    for target, own, other in [("人工髋关节", "髋关节", "膝关节"), ("人工膝关节", "膝关节", "髋关节")]:
        for text, category in [(own, "候选相关"), (other, "明确无关")]:
            rules.append(
                {
                    "fields": [name],
                    "op": "contains",
                    "value": text,
                    "category": category,
                    "when": [{"field": "target_category", "value": target}],
                }
            )
    return {
        **{key: model[key] for key in ["connection", "path", "model"]},
        "max_calls": 30,
        "result_prefix": PREFIX,
        "dictionary": {"id": "wst364.8-2023-cv04.30.002", "field": "study_exam_part"},
        "classification_fields": [
            {"field": field, "role": role}
            for field, role in [
                (name, "evidence"),
                ("study_chk_desc", "evidence"),
                ("target_category", "context"),
                ("study_exam_part", "context"),
                ("study_proj_name", "context"),
                ("study_ckpt_name", "context"),
                ("study_chk_modality", "context"),
            ]
        ],
        "category_routes": [{"category": "候选相关", "continue": True}, {"category": "明确无关", "continue": False}],
        "rules": rules,
        "ambiguity_hints": ["未包含", "不包含", "动脉", "静脉", "造影"],
        "conflicts": [
            {
                "category": category,
                "field": name,
                "contains": technique,
                "when": [{"field": "study_chk_modality", "value": modality}],
            }
            for category in ["候选相关", "明确无关"]
            for technique, modality in [("CT", "DR"), ("MRI", "DR"), ("MRI", "CT")]
        ],
        "business_guidance": (
            "判断这次检查是否可作为当前 target_category 目标关节的候选检查，不是重新判断耗材类别。"
            "标准名称已由字典解释，不要猜码、补码或改写含义。结合完整检查技术名称和该检查的原始描述。"
            "明确相符可判候选相关，明确不相关判明确无关；下肢、近髋等宽泛描述须结合已有描述判断，"
            "不能只凭下肢两字或目标类别推断实际覆盖。仅有下肢血管检查名称而无关节相关依据时判无法确定。"
            "候选不是影像覆盖确认，也不是发现假体或已经能计数。保留左/右/双侧，不由检查侧别推定耗材侧别；"
            "明确侧别矛盾、源模态与检查技术明确冲突时判无法确定。"
            "证据必须引用标准名称或检查描述的原文；置信度仅为自报展示。"
        ),
    }


def configure_graph(original):
    graph = deepcopy(original)
    nodes = {n["id"]: n for n in graph["nodes"]}
    study = nodes["Studies"]["config"]
    study.pop("category_match", None)
    for field, output in [
        ("EXAM_PART", "study_exam_part"),
        ("chk_desc", "study_chk_desc"),
        ("proj_name", "study_proj_name"),
    ]:
        if not any(r["output"] == output for r in study["returns"]):
            study["returns"].append({"field": field, "output": output})
    for node_id, field in [("Studies", "study_chk_modality"), ("Series", "series_modality")]:
        conditions = nodes[node_id]["config"]["checks"]["conditions"]
        for item in conditions:
            if item["field"] == field:
                item.update(op="in", value=["DR", "CT"])
    if "StudyRelevance" not in nodes:
        graph["nodes"].insert(
            5,
            {
                "id": "StudyRelevance",
                "label": "StudyRelevance",
                "kind": "classification",
                "config": classification_config(nodes["Classification"]["config"]),
            },
        )
        for edge in graph["edges"]:
            if edge["source"] == "Studies" and edge["target"] == "Series":
                edge["source"] = "StudyRelevance"
        graph["edges"].append({"source": "Studies", "target": "StudyRelevance", "port": "data", "input": "data"})
    for index, node in enumerate(graph["nodes"]):
        node["position"] = {"x": (index % 5) * 410, "y": (index // 5) * 450}
    nodes["Images"]["config"]["collection"]["item_context"] = [
        "RPT_NO",
        "study_primary_id",
        "study_ris_study_id",
        "series_id",
        "series_modality",
        "study_exam_part",
        PREFIX + "_code_name",
        PREFIX + "_code_version",
        PREFIX + "_code_source",
        PREFIX,
        PREFIX + "_method",
        PREFIX + "_reason",
        PREFIX + "_evidence_text",
    ]
    nodes["Observation"]["config"]["evidence_context_field"] = "image_manifest_context"
    for check in nodes["Results"]["config"]["obligation"]["checks"]:
        if not any(r["node"] == "StudyRelevance" for r in check["results"]):
            check["results"].append(
                {
                    "node": "StudyRelevance",
                    "port": "issues",
                    "status": "uncompared",
                    "reason_field": PREFIX + "_reason",
                    "fallback": True,
                }
            )
    return graph
