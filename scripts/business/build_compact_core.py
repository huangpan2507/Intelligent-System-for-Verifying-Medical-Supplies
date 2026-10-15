"""Build the eleven-node configuration from the reviewed core flow; no source writes."""

from copy import deepcopy

from langflow.business.classification import RESULT_FIELDS
from langflow.business.field_schema import document_evidence

from scripts.business.compact_classification import core_config
from scripts.business.study_relevance import configure_graph


def build_graph(original, settlement_fields):
    old = {n["label"]: n for n in original["nodes"]}
    nodes, edges = [], []

    def add(node_id, kind, config, source=None, port="data"):
        index = len(nodes)
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "label": node_id,
                "config": config,
                "position": {"x": (index % 5) * 410, "y": (index // 5) * 450},
            }
        )
        if source:
            edges.append({"source": source, "target": node_id, "port": port, "input": "data"})

    add("Request", "taskinput", {})
    nodes[-1]["label"] = "Task Start"
    add("Settlements", "database", deepcopy(old["Settlements"]["config"]), "Request")
    add("SettlementChecks", "validate", deepcopy(old["SettlementChecks"]["config"]), "Settlements")
    model = old["NameModel"]["config"]
    classification = core_config(model)
    add("Classification", "classification", classification, "SettlementChecks", "valid")
    study = deepcopy(old["Studies"]["config"])
    study.update(
        {
            "keys": old["SettlementStudies"]["config"]["keys"],
            "source_identity": old["StudyIdentity"]["config"]["identity"],
            "source_required": old["StudyIdentity"]["config"]["required"],
            "returns": [
                {"field": f, "output": "study_" + f}
                for f in [
                    "organ_code",
                    "system_id",
                    "ris_study_id",
                    "name",
                    "cardno",
                    "op_em_hp_ex_no",
                    "ckpt_name",
                    "chk_modality",
                ]
            ]
            + [
                {"field": "link_id", "output": "study_primary_id"},
                {"field": "op_em_hp_ex_mark", "output": "study_visit_type", "type": "text"},
                {"field": "chk_dt", "output": "checked_at", "type": "datetime", "timezone": "Asia/Shanghai"},
            ],
            "checks": {
                "required": ["study_primary_id", "checked_at"],
                "conditions": [c for c in old["StudyChecks"]["config"]["conditions"] if c["field"] != "_match_status"],
            },
        }
    )
    add("Studies", "databaselookup", study, "Classification")
    series = deepcopy(old["Series"]["config"])
    series.update(
        {
            "keys": [{"left": "study_" + f, "right": f} for f in ["organ_code", "system_id", "ris_study_id"]],
            "source_identity": old["SeriesIdentity"]["config"]["identity"],
            "source_required": old["SeriesIdentity"]["config"]["required"],
            "returns": [
                {"field": field, "output": name}
                for field, name in [
                    ("global_id", "series_id"),
                    ("link_id", "link_id"),
                    ("chk_modality", "series_modality"),
                ]
            ],
            "checks": {
                "required": ["series_id", "link_id"],
                "conditions": [c for c in old["SeriesChecks"]["config"]["conditions"] if c["field"] != "_match_status"],
            },
        }
    )
    add("Series", "databaselookup", series, "Studies")
    images = deepcopy(old["Images"]["config"])
    images.pop("context_fields", None)
    images["collection"] = {
        "group_by": ["_identity"],
        "retain_fields": [*settlement_fields, *(f["name"] for f in RESULT_FIELDS), "_representative_row_id"],
        "address_fields": ["domain", "file_path"],
        "item_keys": ["study_instance_uid", "series_instance_uid", "sop_instance_uid"],
        "output": "image_manifest",
    }
    images["field_evidence"] = document_evidence(
        images, images["fields"], old["Images"]["config"]["field_evidence"]["reference"]
    )
    add("Images", "api", images, "Series")
    observation = deepcopy(old["Observation"]["config"])
    observation.pop("unit_field", None)
    observation.pop("unit_value", None)
    observation["result_checks"] = deepcopy(old["ObservationChecks"]["config"])
    observation["result_checks"]["conditions"] = [
        c for c in observation["result_checks"]["conditions"] if c["field"] != "observed_unit"
    ]
    add("Observation", "imaging", observation, "Images")
    comparison = deepcopy(old["CompareQuantityFee"]["config"])
    comparison["calculations"] = [
        {"field": "_representative_row_id", "output": "unit_row_id", "operation": "copy"},
        {"output": "settled_amount", "operation": "expression", "expression": "CNT * PRIC"},
        {"output": "observed_amount", "operation": "expression", "expression": "recognized_quantity * PRIC"},
    ]
    for item, name in zip(
        comparison["comparisons"], ["category_status", "quantity_status", "amount_status"], strict=True
    ):
        item["output"] = name
    add("Compare", "compare", comparison, "Observation")
    output = deepcopy(old["Results"]["config"])
    output["columns"] = [name for name in output["columns"] if name != "unit"]
    output["obligation"] = {
        "mode": "verification",
        "sources": [{"node": "Settlements", "identity": "SettlementChecks"}],
        "checks": [
            {
                "name": name,
                "units": {"node": "Classification", "port": "data"},
                "results": [
                    {"node": "Compare", "port": "data", "status_field": field, "evidence_field": "evidence_ref"}
                ],
            }
            for name, field in [
                ("category", "category_status"),
                ("quantity", "quantity_status"),
                ("fee", "amount_status"),
            ]
        ],
        "dispositions": [
            {
                "node": "Classification",
                "port": "issues",
                "status_field": "classification_disposition",
                "reason_field": "classification_disposition_reason",
            },
            *[
                {"node": name, "port": "issues", "status": "uncompared", "reason": "incomplete_evidence"}
                for name in ["Studies", "Series", "Images", "Observation"]
            ],
        ],
    }
    add("Results", "output", output, "Compare")
    graph = configure_graph({"nodes": nodes, "edges": edges})
    next(n for n in graph["nodes"] if n["kind"] == "output")["config"] = {
        "name": output["name"],
        "result_template": "hip_knee_v1",
    }
    return graph
