# ruff: noqa: S608 - identifiers and literals use the shared SQL quoting functions.
"""Configurable rules and model fallback with one stable, evidence-bearing result contract."""

from langflow.business import code_dictionary
from langflow.business.classification_config import effective_config, model_prompt
from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.expressions import predicate
from langflow.business.sources import model_read

RESULT_FIELDS = [
    {"name": name, "type": kind}
    for name, kind in [
        ("target_category", "text"),
        ("classification_method", "text"),
        ("classification_reason", "text"),
        ("classification_evidence_field", "text"),
        ("classification_evidence_text", "text"),
        ("classification_confidence", "number"),
        ("classification_ambiguity", "text"),
    ]
]
DISPOSITION_FIELDS = [
    {"name": "classification_disposition", "type": "text"},
    {"name": "classification_disposition_reason", "type": "text"},
]
MODEL_FIELDS = [
    {"name": "model_" + name, "type": kind, "nullable": False}
    for name, kind in [
        ("category", "text"),
        ("reason", "text"),
        ("evidence_field", "text"),
        ("evidence_text", "text"),
        ("confidence", "number"),
    ]
]


def output_names(config):
    prefix = config.get("result_prefix", "classification")
    return {
        field["name"]: (prefix if field["name"] == "target_category" else prefix + field["name"][14:])
        if prefix != "classification"
        else field["name"]
        for field in [*RESULT_FIELDS, *DISPOSITION_FIELDS]
    }


def output_fields(config):
    names = output_names(config)
    return [{**f, "name": names[f["name"]]} for f in [*RESULT_FIELDS, *DISPOSITION_FIELDS]]


def validate_config(config, fields):
    config = effective_config(config)
    code_dictionary.validate(config, fields)
    fields = [*fields, *(f["name"] for f in code_dictionary.fields(config))]
    categories = set(config["categories"])
    if not categories or len(categories) != len(config["categories"]) or not config["target_categories"]:
        msg = "Declare unique categories and at least one continuing category"
        raise ValueError(msg)
    if len(config["input_fields"]) != len(set(config["input_fields"])):
        msg = "Select each classification field once"
        raise ValueError(msg)
    if not set(config["input_fields"]) <= set(fields):
        msg = "Classification fields must exist in the upstream dataset"
        raise ValueError(msg)
    if config["unknown_category"] in categories or not set(config["target_categories"]) <= categories:
        msg = "Targets must be declared categories; unknown must be a separate category"
        raise ValueError(msg)
    if not config["evidence_fields"] or not set(config["evidence_fields"]) <= set(config["input_fields"]):
        msg = "Evidence fields must be nonempty and included in model inputs"
        raise ValueError(msg)
    for rule in config["rules"]:
        predicate({"conditions": rule.get("when", [])}, config["input_fields"])
        if rule["op"] == "contains_all":
            if not rule.get("keywords") or any(not word.strip() for word in rule["keywords"]):
                msg = "Contains-all rules need nonempty keywords"
                raise ValueError(msg)
        elif not rule.get("value", "").strip():
            msg = "Contains/equal rules need comparison text"
            raise ValueError(msg)
        if rule["category"] not in categories or not rule["fields"]:
            msg = "Each rule needs a declared category and input fields"
            raise ValueError(msg)
        if not set(rule["fields"]) <= set(config["evidence_fields"]):
            msg = "Rules must cite configured evidence fields"
            raise ValueError(msg)
    if any(c["category"] not in categories for c in config.get("conflicts", [])):
        msg = "Conflict category is not declared"
        raise ValueError(msg)
    if any(c["field"] not in fields for c in config.get("conflicts", [])):
        msg = "Conflict fields must exist in the upstream dataset"
        raise ValueError(msg)
    for item in config.get("conflicts", []):
        predicate({"conditions": item.get("when", [])}, config["input_fields"])
    if any(not hint.strip() for hint in config.get("ambiguity_hints", [])):
        msg = "Ambiguity hints cannot be empty"
        raise ValueError(msg)
    reserved = {f["name"] for f in [*output_fields(config), *MODEL_FIELDS]} | {"_classification_conflict"}
    if reserved.intersection(fields):
        msg = "Classification output fields already exist"
        raise ValueError(msg)


def match(field, value, op="contains"):
    source = f"coalesce(CAST({ident(field)} AS VARCHAR), '')"
    if op == "contains":
        return f"contains({source}, {literal(value)})"
    if op == "eq":
        return f"{source}={literal(value)}"
    if op == "contains_all" and value and all(word.strip() for word in value):
        return "(" + " AND ".join(f"contains({source}, {literal(word)})" for word in value) + ")"
    msg = "Unknown match operation or empty keywords"
    raise ValueError(msg)


def conflict(config, category):
    return (
        " OR ".join(
            (
                f"({category}={literal(c['category'])} AND {match(c['field'], c['contains'])} "
                f"AND ({predicate({'conditions': c.get('when', [])}, config['input_fields'])}))"
            )
            for c in config.get("conflicts", [])
        )
        or "FALSE"
    )


def rule_query(config, source):
    config = effective_config(config)
    names = {key: ident(value) for key, value in output_names(config).items()}
    hits = [
        (
            rule,
            f,
            (
                f"({match(f, rule.get('keywords') if rule['op'] == 'contains_all' else rule['value'], rule['op'])}) "
                f"AND ({predicate({'conditions': rule.get('when', [])}, config['input_fields'])})"
            ),
        )
        for rule in config["rules"]
        for f in rule["fields"]
    ]
    hints = [
        f"CASE WHEN ({sql}) AND ({match(field, hint)}) THEN "
        f"struct_pack(field := {literal(field)}, original := CAST({ident(field)} AS VARCHAR), "
        f"hint := {literal(hint)}) END"
        for _, field, sql in hits
        for hint in config.get("ambiguity_hints", [])
    ]
    ambiguity = f"to_json(list_filter([{', '.join(hints)}], x -> x IS NOT NULL))" if hints else "'[]'"
    category_hits = [
        "(" + (" OR ".join(sql for r, _, sql in hits if r["category"] == c) or "FALSE") + ")"
        for c in config["categories"]
    ]
    overlap = " + ".join(f"CAST({h} AS INTEGER)" for h in category_hits)
    unknown = literal(config["unknown_category"])
    category = (
        ("CASE " + " ".join(f"WHEN {sql} THEN {literal(r['category'])}" for r, _, sql in hits) + f" ELSE {unknown} END")
        if hits
        else unknown
    )
    field = (
        ("CASE " + " ".join(f"WHEN {sql} THEN {literal(f)}" for _, f, sql in hits) + " ELSE '' END") if hits else "''"
    )
    quote = (
        ("CASE " + " ".join(f"WHEN {sql} THEN CAST({ident(f)} AS VARCHAR)" for _, f, sql in hits) + " ELSE '' END")
        if hits
        else "''"
    )
    bad = f"coalesce((({overlap}) > 1 OR ({conflict(config, category)})), FALSE)"
    resolved = code_dictionary.resolved(config)
    return (
        f"SELECT *, {bad} AS _classification_conflict, "
        f"CASE WHEN {bad} OR ({ambiguity}<>'[]') OR NOT ({resolved}) THEN {unknown} "
        f"ELSE {category} END AS {names['target_category']}, "
        f"'rule' AS {names['classification_method']}, "
        f"CASE WHEN NOT ({resolved}) THEN 'unresolved_dictionary_code' WHEN {bad} THEN 'conflicting_evidence' "
        f"WHEN ({ambiguity}<>'[]') THEN 'ambiguity_hint' ELSE 'configured_rule' END "
        f"AS {names['classification_reason']}, "
        f"CAST({ambiguity} AS VARCHAR) AS {names['classification_ambiguity']}, "
        f"CASE WHEN {bad} THEN '' ELSE {field} END AS {names['classification_evidence_field']}, "
        f"CASE WHEN {bad} THEN '' ELSE {quote} END AS {names['classification_evidence_text']}, "
        f"NULL::DECIMAL(38,6) AS {names['classification_confidence']} FROM {source}"
    )


def save_projection(store, node, query, source, *, port="data", parents=None, details=None):
    parents = list(dict.fromkeys([source["id"], *(parents or [])]))
    ref = store.query(
        node,
        query,
        port=port,
        parents=parents,
        details={"blockers": store.get(source["id"]).provenance.get("blockers", []), **(details or {})},
    )
    store.link(
        ref,
        f"SELECT {ident(ROW_ID)} row_id, {literal(source['id'])} parent_id, "
        f"{ident(ROW_ID)} parent_row_id FROM {store.relation(ref['id'])}",
        [source["id"]],
    )
    return ref


def execute(runtime, node, source):
    store, config = runtime.store, effective_config(node["config"])
    node_id = runtime.prefix + node["id"]
    validate_config(config, [f["name"] for f in source["fields"]])
    if config.get("dictionary"):
        source = save_projection(
            store,
            node_id,
            code_dictionary.query(config, store.relation(source["id"])),
            source,
            port="dictionary",
            details={"dictionary": config["dictionary"]},
        )
    names = {key: ident(value) for key, value in output_names(config).items()}
    category, reason = names["target_category"], names["classification_reason"]
    disposition, disposition_reason = names["classification_disposition"], names["classification_disposition_reason"]
    ambiguity = names["classification_ambiguity"]
    signals = save_projection(store, node_id, rule_query(config, store.relation(source["id"])), source, port="rules")
    unknown = literal(config["unknown_category"])
    original = [f["name"] for f in source["fields"]]
    resolved = code_dictionary.resolved(config)
    model_source = save_projection(
        store,
        node_id,
        f"SELECT {', '.join(map(ident, original))}, _classification_conflict, {ambiguity} "
        f"FROM {store.relation(signals['id'])} WHERE {category}={unknown} AND ({resolved})",
        source,
        port="model_input",
        parents=[signals["id"]],
    )
    model_config = {**config, "fields": MODEL_FIELDS, "mode": "openai", "prompt": model_prompt(node["config"])}
    responses = model_read(
        store,
        node_id,
        model_config,
        runtime.connection(config["connection"]),
        runtime.settings,
        model_source,
        port_prefix="model_",
    )
    modeled = (
        "(" + " UNION ALL BY NAME ".join(f"SELECT * FROM {store.relation(r['id'])}" for r in responses.values()) + ")"
    )
    quote_ok = " OR ".join(
        f"(model_evidence_field={literal(f)} AND contains(CAST({ident(f)} AS VARCHAR), model_evidence_text))"
        for f in config["evidence_fields"]
    )
    allowed = ", ".join(literal(c) for c in config["categories"])
    valid = (
        f"coalesce((NOT _classification_conflict AND coalesce(_issue_reason,'')='' "
        f"AND model_category IN ({allowed}) AND NOT ({conflict(config, 'model_category')}) "
        f"AND trim(model_reason)<>'' AND trim(model_evidence_text)<>'' AND ({quote_ok}) "
        "AND model_confidence BETWEEN 0 AND 1), FALSE)"
    )
    model_query = (
        f"SELECT {', '.join(map(ident, original))}, "
        f"CASE WHEN {valid} THEN model_category ELSE {unknown} END AS {category}, "
        f"'model' AS {names['classification_method']}, "
        f"CASE WHEN {valid} THEN model_reason ELSE 'invalid_or_conflicting_evidence' END AS {reason}, "
        f"model_evidence_field AS {names['classification_evidence_field']}, "
        f"model_evidence_text AS {names['classification_evidence_text']}, "
        f"CASE WHEN model_confidence BETWEEN 0 AND 1 THEN model_confidence END "
        f"AS {names['classification_confidence']}, "
        f"{ambiguity} FROM {modeled}"
    )
    columns = ", ".join([*map(ident, original), *(names[f["name"]] for f in RESULT_FIELDS)])
    combined = save_projection(
        store,
        node_id,
        f"SELECT {columns} FROM {store.relation(signals['id'])} WHERE {category}<>{unknown} OR NOT ({resolved}) "
        f"UNION ALL BY NAME {model_query}",
        source,
        port="classification_results",
        parents=[signals["id"], *(r["id"] for r in responses.values())],
    )
    targets = ", ".join(literal(c) for c in config["target_categories"])
    routed_query = (
        f"SELECT *, CASE WHEN {category} IN ({targets}) THEN 'continue' "
        f"WHEN {category}={unknown} THEN 'uncompared' ELSE 'excluded' END AS {disposition}, "
        f"CASE WHEN {category} IN ({targets}) THEN 'target_category' "
        f"WHEN {category}={unknown} THEN {reason} ELSE 'non_target_category' END "
        f"AS {disposition_reason} FROM {store.relation(combined['id'])}"
    )
    with store.engine() as db:
        counts = dict(db.execute(f"SELECT {disposition}, count(*) FROM ({routed_query}) GROUP BY 1").fetchall())
    return {
        port: save_projection(
            store,
            node_id,
            f"SELECT * FROM ({routed_query}) WHERE {where}",
            combined,
            port=port,
            details={
                "blocking_rows": counts.get("uncompared", 0) if port == "issues" else 0,
                "classification_counts": {k: counts.get(k, 0) for k in ["continue", "excluded", "uncompared"]},
                "classification_result_field": output_names(config)["target_category"],
            },
        )
        for port, where in {"data": f"{disposition}='continue'", "issues": f"{disposition}<>'continue'"}.items()
    }
