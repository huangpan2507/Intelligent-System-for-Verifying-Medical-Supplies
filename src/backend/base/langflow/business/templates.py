"""Examples are graph configuration, never alternate execution paths."""

from langflow.business.validate_migration import migrate_graph


def node(node_id, kind, config, x=0, y=0):
    return {"id": node_id, "kind": kind, "label": node_id, "config": config, "position": {"x": x, "y": y}}


def edge(source, target, port="data", input_port="data"):
    return {"source": source, "target": target, "port": port, "input": input_port}


def comparison(connections=None):
    connections = connections or {}
    graph = {
        "nodes": [
            node("Orders", "database", {"connection": connections.get("orders", ""), "table": "orders"}, 0, 0),
            node("Payments", "database", {"connection": connections.get("payments", ""), "table": "payments"}, 0, 400),
            node(
                "OrderChecks",
                "validate",
                {
                    "required": ["order_no", "amount"],
                    "identity": {"name": "order", "namespace": "orders", "keys": ["order_no"]},
                },
                350,
                0,
            ),
            node(
                "PaymentChecks",
                "validate",
                {
                    "required": ["payment_id", "biz_no", "amount"],
                    "identity": {"name": "payment", "namespace": "payments", "keys": ["payment_id"]},
                },
                350,
                400,
            ),
            node(
                "PaymentTotals",
                "aggregate",
                {"group_by": ["biz_no"], "metrics": [{"field": "amount", "operation": "sum", "output": "paid_total"}]},
                700,
                400,
            ),
            node(
                "Match",
                "join",
                {"keys": [{"left": "order_no", "right": "biz_no"}], "how": "full", "cardinality": "one_to_one"},
                1050,
                0,
            ),
            node(
                "CompareAmounts",
                "compare",
                {"comparisons": [{"left": "left_amount", "right": "right_paid_total", "mode": "numeric"}]},
                1400,
                0,
            ),
            node(
                "Results",
                "output",
                {
                    "name": "Comparison results",
                    "primary": True,
                    "obligation": {
                        "mode": "verification",
                        "sources": [
                            {"node": "Orders", "identity": "OrderChecks"},
                            {"node": "Payments", "identity": "PaymentChecks"},
                        ],
                        "checks": [
                            {
                                "name": "amount",
                                "units": {"node": "Match", "port": "data"},
                                "results": [
                                    {"node": "CompareAmounts", "port": "data", "status_field": "_comparison_status"}
                                ],
                            }
                        ],
                        "dispositions": [
                            {"node": name, "port": "data", "status": "issue", "reason": reason}
                            for name, reason in [
                                ("OrderIssues", "invalid_order"),
                                ("PaymentIssues", "invalid_payment"),
                                ("JoinIssues", "ambiguous_business_key"),
                            ]
                        ],
                    },
                },
                1750,
                0,
            ),
            node("OrderIssues", "output", {"name": "Order data issues"}, 700, -350),
            node("PaymentIssues", "output", {"name": "Payment data issues"}, 700, 800),
            node("JoinIssues", "output", {"name": "Ambiguous join keys"}, 1400, 400),
        ],
        "edges": [
            edge("Orders", "OrderChecks"),
            edge("Payments", "PaymentChecks"),
            edge("PaymentChecks", "PaymentTotals", "valid"),
            edge("OrderChecks", "Match", "valid", "left"),
            edge("PaymentTotals", "Match", input_port="right"),
            edge("Match", "CompareAmounts"),
            edge("CompareAmounts", "Results"),
            edge("OrderChecks", "OrderIssues", "issues"),
            edge("PaymentChecks", "PaymentIssues", "issues"),
            edge("Match", "JoinIssues", "issues"),
        ],
    }
    # Existing template issue branches describe errors, not merged duplicate notices.
    return migrate_graph(graph)


def consumables(connection=""):
    """Synthetic professional assumptions are explicit template configuration, never engine branches."""
    from langflow.business.datasets import ROW_ID

    nodes, edges = [], []

    def add(name, kind, config, source=None, port="data"):
        nodes.append(node(name, kind, config, (len(nodes) % 7) * 380, (len(nodes) // 7) * 380))
        if source:
            edges.append(edge(source, name, port))
        return name

    def read(name, path, fields, source=None, body=None, contexts=(), scope="object"):
        return add(
            name,
            "api",
            {
                "connection": connection,
                "path": path,
                "items_path": "items",
                "pagination": "none",
                "method": "POST" if name == "Settlements" else "GET",
                "body": body or {},
                "fields": [{"name": n, "type": t} for n, t in fields],
                "context_fields": list(contexts),
                "completeness": {
                    "scope": scope,
                    "basis": "Synthetic v2: complete response for the explicitly requested scope",
                    "complete_path": "complete",
                },
            },
            source,
        )

    def output(name, source, port="data"):
        return add(name, "output", {"name": name}, source, port)

    def transform(name, source, mapping, select):
        return add(
            name,
            "transform",
            {
                "select": select,
                "transforms": [
                    {"operation": "copy", "field": origin, "output": target} for target, origin in mapping.items()
                ],
            },
            source,
        )

    def join(name, left, right, keys, cardinality="one_to_one"):
        add(
            name,
            "join",
            {"keys": [{"left": a, "right": b} for a, b in keys], "how": "left", "cardinality": cardinality},
        )
        edges.extend([edge(left, name, input_port="left"), edge(right, name, input_port="right")])

    add(
        "Request",
        "parameters",
        {
            "parameters": [
                {"name": "hospital", "type": "string", "required": True, "default": "synthetic-hospital"},
                {"name": "start", "type": "string", "required": True, "default": "2024-01-01"},
                {"name": "end", "type": "string", "required": True, "default": "2027-01-01"},
                {
                    "name": "scenario",
                    "type": "string",
                    "default": "baseline",
                    "enum": ["baseline", "adversarial"],
                    "description": "Synthetic fixtures only",
                },
            ]
        },
    )
    read(
        "Settlements",
        "/business/settlements",
        [
            ("detail_id", "text"),
            ("patient_id", "text"),
            ("hospital_id", "text"),
            ("encounter_id", "text"),
            ("catalog_code", "text"),
            ("medical_consumable", "boolean"),
            ("insurance_paid", "boolean"),
            ("quantity", "number"),
            ("unit", "text"),
            ("unit_price", "number"),
            ("billed_amount", "number"),
        ],
        "Request",
        {k: {"parameter": k} for k in ["hospital", "start", "end", "scenario"]},
        scope="range",
    )
    add(
        "SettlementChecks",
        "validate",
        {"identity": {"name": "settlement_detail", "namespace": "synthetic-settlement-v2", "keys": ["detail_id"]}},
        "Settlements",
    )
    output("InvalidSettlements", "SettlementChecks", "issues")
    add(
        "Facts",
        "filter",
        {
            "conditions": [
                {"field": "insurance_paid", "op": "eq", "value": True},
                {"field": "medical_consumable", "op": "eq", "value": True},
            ]
        },
        "SettlementChecks",
        "valid",
    )
    output("UnknownFacts", "Facts", "unknown")
    output("OutsideFacts", "Facts", "unmatched")
    read("Catalog", "/business/catalog", [("code", "text"), ("category", "text")], scope="range")
    add(
        "Classification",
        "join",
        {"keys": [{"left": "catalog_code", "right": "code"}], "how": "left", "cardinality": "many_to_one"},
    )
    edges += [edge("Facts", "Classification", "matched", "left"), edge("Catalog", "Classification", input_port="right")]
    output("AmbiguousCatalog", "Classification", "issues")
    add(
        "Targets",
        "filter",
        {"conditions": [{"field": "right_category", "op": "in", "value": ["hip_prosthesis", "knee_prosthesis"]}]},
        "Classification",
    )
    output("UnknownCategories", "Targets", "unknown")
    output("OutsideCategories", "Targets", "unmatched")
    groups = ["left_patient_id", "left_hospital_id", "left_encounter_id", "right_category", "left_unit"]
    add(
        "TargetChecks",
        "validate",
        {"required": [*groups, "left_quantity"], "conditions": [{"field": "left_quantity", "op": "ge", "value": 0}]},
        "Targets",
        "matched",
    )
    output("InvalidTargets", "TargetChecks", "issues")
    add(
        "Units",
        "aggregate",
        {
            "group_by": groups,
            "metrics": [
                {"field": "left_quantity", "operation": "sum", "output": "settled_quantity"},
            ],
        },
        "TargetChecks",
        "valid",
    )
    # Fees have their own prerequisites: a missing price must not erase a valid quantity observation.
    add(
        "FeeTotals",
        "aggregate",
        {
            "group_by": groups,
            "metrics": [
                {"field": "left_billed_amount", "operation": "sum", "output": "settled_amount"},
                {"field": "left_unit_price", "operation": "min", "output": "min_price"},
                {"field": "left_unit_price", "operation": "max", "output": "max_price"},
            ],
        },
        "TargetChecks",
        "valid",
    )
    read(
        "Studies",
        "/business/studies",
        [
            ("study_primary_id", "text"),
            ("patient_id", "text"),
            ("hospital_id", "text"),
            ("encounter_id", "text"),
            ("scope_confirmed", "boolean"),
        ],
        "Units",
        {
            "system_patient_id": {"field": "left_patient_id"},
            "organ_code": {"field": "left_hospital_id"},
            "op_em_hp_ex_no": {"field": "left_encounter_id"},
        },
        contexts=[ROW_ID, "left_patient_id", "left_hospital_id", "left_encounter_id"],
    )
    add(
        "StudyScope",
        "validate",
        {
            "required": ["study_primary_id"],
            "conditions": [
                {"field": "patient_id", "op": "eq", "right_field": "_context_left_patient_id"},
                {"field": "hospital_id", "op": "eq", "right_field": "_context_left_hospital_id"},
                {"field": "encounter_id", "op": "eq", "right_field": "_context_left_encounter_id"},
                {"field": "scope_confirmed", "op": "eq", "value": True},
            ],
        },
        "Studies",
    )
    add(
        "StudyContext",
        "transform",
        {"transforms": [{"operation": "copy", "field": "_context_" + ROW_ID, "output": "unit_row_id"}]},
        "StudyScope",
        "valid",
    )
    read(
        "Series",
        "/business/series",
        [("series_id", "text")],
        "StudyContext",
        {"study_primary_id": {"field": "study_primary_id"}},
        contexts=["unit_row_id"],
    )
    transform("SeriesContext", "Series", {"unit_row_id": "_context_unit_row_id"}, ["series_id"])
    read(
        "Images",
        "/business/images",
        [("sop_instance_uid", "text"), ("file_ref", "text")],
        "SeriesContext",
        {"series_id": {"field": "series_id"}},
        contexts=["unit_row_id"],
    )
    transform("ImageContext", "Images", {"unit_row_id": "_context_unit_row_id"}, ["sop_instance_uid", "file_ref"])
    add(
        "ImageIdentities",
        "validate",
        {
            "required": ["file_ref"],
            "identity": {
                "name": "unit_image",
                "namespace": "synthetic-imaging-v2",
                "keys": ["unit_row_id", "sop_instance_uid"],
            },
        },
        "ImageContext",
    )
    add(
        "Manifests",
        "aggregate",
        {
            "group_by": ["unit_row_id"],
            "metrics": [{"field": "file_ref", "operation": "collect", "output": "image_manifest"}],
        },
        "ImageIdentities",
        "valid",
    )
    join("UnitEvidence", "Units", "Manifests", [(ROW_ID, "unit_row_id")])
    transform(
        "ObservationInput",
        "UnitEvidence",
        {
            **{f: "left_" + f for f in [*groups, "settled_quantity"]},
            "image_manifest": "right_image_manifest",
            "_blocking_reason": "left__blocking_reason",
        },
        ["right__blocking_reason"],
    )
    add("EvidenceChecks", "validate", {"required": ["image_manifest"]}, "ObservationInput")
    add(
        "Imaging",
        "imaging",
        {
            "connection": connection,
            "path": "/business/imaging",
            "patient_field": "left_patient_id",
            "hospital_field": "left_hospital_id",
            "encounter_field": "left_encounter_id",
            "category_field": "right_category",
            "evidence_field": "image_manifest",
            "max_calls": 1000,
        },
        "EvidenceChecks",
        "valid",
    )
    add(
        "ObservationChecks",
        "validate",
        {
            "required": ["recognized_category", "evidence_ref"],
            "conditions": [
                {"field": "recognition_confirmed", "op": "eq", "value": True},
            ],
        },
        "Imaging",
    )
    add(
        "CompareCategory",
        "compare",
        {"comparisons": [{"left": "right_category", "right": "recognized_category"}]},
        "ObservationChecks",
        "valid",
    )
    output("CategoryResults", "CompareCategory")
    add(
        "QuantityChecks",
        "validate",
        {
            "required": ["recognized_quantity"],
            "conditions": [
                {"field": "recognized_quantity", "op": "ge", "value": 0},
                {"field": "coverage_confirmed", "op": "eq", "value": True},
                {"field": "observed_unit", "op": "eq", "right_field": "left_unit"},
                {"field": "recognized_category", "op": "eq", "right_field": "right_category"},
            ],
        },
        "ObservationChecks",
        "valid",
    )
    add(
        "Compare",
        "compare",
        {"comparisons": [{"left": "settled_quantity", "right": "recognized_quantity", "mode": "numeric"}]},
        "QuantityChecks",
        "valid",
    )
    output("Results", "Compare")
    join("FeeEvidence", "Compare", "FeeTotals", [(g, g) for g in groups])
    add(
        "FeeChecks",
        "validate",
        {
            "required": ["right_min_price", "right_max_price", "right_settled_amount"],
            "conditions": [
                {"field": "right_min_price", "op": "eq", "right_field": "right_max_price"},
                {"field": "right_min_price", "op": "ge", "value": 0},
            ],
        },
        "FeeEvidence",
    )
    add(
        "FeeCalculation",
        "transform",
        {
            "transforms": [
                {
                    "operation": "expression",
                    "expression": "left_recognized_quantity * right_min_price",
                    "output": "observed_amount",
                }
            ]
        },
        "FeeChecks",
        "valid",
    )
    add(
        "CompareFee",
        "compare",
        {"comparisons": [{"left": "right_settled_amount", "right": "observed_amount", "mode": "numeric"}]},
        "FeeCalculation",
    )
    output("FeeResults", "CompareFee")
    failures = [
        "Studies",
        "StudyScope",
        "Series",
        "Images",
        "ImageIdentities",
        "UnitEvidence",
        "EvidenceChecks",
        "Imaging",
        "ObservationChecks",
        "QuantityChecks",
        "FeeEvidence",
        "FeeChecks",
    ]
    for name in failures:
        output("UnverifiedImages" if name == "Imaging" else name + "Issues", name, "issues")
    common = [{"node": n, "port": "issues", "status": "uncompared", "reason": n + "_unconfirmed"} for n in failures[:9]]
    checks = []
    for name, output_name, extra in [
        ("category", "CategoryResults", []),
        ("quantity", "Results", ["QuantityChecks"]),
        ("fee", "FeeResults", ["QuantityChecks", "FeeEvidence", "FeeChecks"]),
    ]:
        checks.append(
            {
                "name": name,
                "units": {"node": "Units", "port": "data"},
                "results": [
                    {
                        "node": output_name,
                        "port": "data",
                        "status_field": "_comparison_status",
                        "evidence_field": "left_evidence_ref" if name == "fee" else "evidence_ref",
                    },
                    *common,
                    *[
                        {"node": n, "port": "issues", "status": "uncompared", "reason": n + "_unconfirmed"}
                        for n in extra
                    ],
                ],
            }
        )
    dispositions = [
        {"node": name, "port": "data", "status": status, "reason": reason}
        for name, status, reason in [
            ("InvalidSettlements", "issue", "identity_missing_or_conflicting"),
            ("UnknownFacts", "uncompared", "payment_or_consumable_unknown"),
            ("OutsideFacts", "excluded", "outside_payment_or_consumable_scope"),
            ("OutsideCategories", "excluded", "outside_target_categories"),
            ("UnknownCategories", "uncompared", "catalog_category_unknown"),
            ("AmbiguousCatalog", "issue", "catalog_ambiguous"),
            ("InvalidTargets", "uncompared", "target_processing_prerequisites_missing"),
        ]
    ]
    next(n for n in nodes if n["id"] == "Results")["config"].update(
        primary=True,
        obligation={
            "mode": "verification",
            "sources": [{"node": "Settlements", "identity": "SettlementChecks"}],
            "checks": checks,
            "dispositions": dispositions,
        },
    )
    from langflow.business.field_schema import document_evidence

    for item in nodes:
        if item["kind"] == "api":
            config = item["config"]
            config["field_evidence"] = document_evidence(
                config, config["fields"], "Bundled synthetic API contract: langflow.business.demo (not a real provider)"
            )
    # Keep both settlement and image identity notices out of failure dispositions.
    return migrate_graph({"nodes": nodes, "edges": edges})


def templates():
    import json
    from pathlib import Path

    return [
        {
            "id": "hip_knee_core",
            "graph": json.loads((Path(__file__).parent / "presets/hip_knee_core.json").read_text()),
        },
        {"id": "regulatory", "graph": {"nodes": [node("Request", "taskinput", {})], "edges": []}},
        {"id": "compare", "graph": comparison()},
        {"id": "consumables", "graph": consumables()},
        {"id": "empty", "graph": {"nodes": [node("Request", "parameters", {"parameters": []})], "edges": []}},
    ]
