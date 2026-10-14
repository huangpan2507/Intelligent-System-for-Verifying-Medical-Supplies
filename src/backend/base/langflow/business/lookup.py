# ruff: noqa: S608 - SQL identifiers/literals are quoted; database keys are bound by SQLAlchemy.
"""Read related records in bounded key batches and preserve both sources' lineage."""

from langflow.business.connections import read_database
from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.relational import TYPES, fields_of, unary_query


def lookup_query(config, left, fields, right):
    additions, errors = [], []
    outputs = [r["output"] for r in config["returns"]]
    if len(outputs) != len(set(outputs)) or set(outputs).intersection(fields):
        msg = "Lookup return names must be unique and must not overwrite upstream fields"
        raise ValueError(msg)
    if any(name.startswith("_") for name in outputs):
        msg = "Lookup return names cannot use reserved names"
        raise ValueError(msg)
    columns = [
        f"l.{ident(f)}"
        for f in fields
        if f not in {ROW_ID, "_match_status", "_issue_reason", "_lookup_input_row_id", "_lookup_source_row_id"}
    ]
    for item in config["returns"]:
        value = original = f"r.{ident(item['field'])}"
        if item.get("type") == "datetime":
            from zoneinfo import ZoneInfo

            zone = item.get("timezone", config.get("timezone", "UTC"))
            ZoneInfo(zone)
            value = f"timezone({literal(zone)}, TRY_CAST({original} AS TIMESTAMP))"
        elif item.get("type"):
            value = f"TRY_CAST({original} AS {TYPES[item['type']]})"
        if item.get("type"):
            errors.append(
                f"CASE WHEN {original} IS NOT NULL AND {value} IS NULL "
                f"THEN {literal('conversion:' + item['output'])} END"
            )
        additions.append(f"{value} AS {ident(item['output'])}")
    if "_issue_reason" in fields:
        errors.insert(0, "nullif(l._issue_reason, '')")
    reason = "concat_ws(';', " + ", ".join(errors) + ")" if errors else "''"
    on = " AND ".join(f"l.{ident(k['left'])}=r.{ident(k['right'])}" for k in config["keys"])
    return (
        f"SELECT {', '.join([*columns, *additions])}, {reason} AS _issue_reason, "
        f"CASE WHEN r.{ident(ROW_ID)} IS NULL THEN 'left_only' ELSE 'matched' END AS _match_status, "
        f"l.{ident(ROW_ID)} AS _lookup_input_row_id, r.{ident(ROW_ID)} AS _lookup_source_row_id, "
        f"row_number() OVER ()-1 AS {ident(ROW_ID)} FROM {left} l LEFT JOIN {right} r ON {on}"
    )


def result_queries(config, source, fields, parameters):
    checks = config.get("checks", {})
    checks = {
        **checks,
        "conditions": [{"field": "_match_status", "op": "eq", "value": "matched"}, *checks.get("conditions", [])],
    }
    queries = unary_query("validate", checks, source, fields, parameters)
    return {"data": queries["valid"], "issues": queries["issues"]}


def execute(runtime, node, source):
    config, store = node["config"], runtime.store
    node_id = runtime.prefix + node["id"]
    left_keys = [k["left"] for k in config["keys"]]

    def key_batches():
        with store.engine() as db:
            cursor = db.execute(
                f"SELECT DISTINCT {', '.join(map(ident, left_keys))} "
                f"FROM {store.relation(source['id'])} WHERE "
                + " AND ".join(f"{ident(f)} IS NOT NULL" for f in left_keys)
            )
            while batch := cursor.fetchmany(500):
                yield batch

    raw = read_database(
        store,
        node_id + "--source",
        runtime.connection(config["connection"]),
        runtime.settings,
        config,
        runtime.parameters,
        key_fields=[k["right"] for k in config["keys"]],
        key_batches=key_batches(),
    )
    remote = raw
    if config.get("source_identity") or config.get("source_required"):
        quality = {"required": config.get("source_required", [])}
        if config.get("source_identity"):
            quality["identity"] = config["source_identity"]
        remote = runtime.run_node(
            {"id": node["id"] + "--source-quality", "kind": "validate", "config": quality}, {"data": [raw]}
        )["valid"]
    joined = store.query(
        node_id,
        lookup_query(config, store.relation(source["id"]), fields_of(source), store.relation(remote["id"])),
        port="associations",
        parents=[source["id"], remote["id"]],
    )
    queries = result_queries(config, store.relation(joined["id"]), fields_of(joined), runtime.parameters)
    outputs = {}
    for port, query in queries.items():
        ref = store.query(
            node_id,
            query,
            port=port,
            parents=[source["id"], remote["id"]],
            details={
                "operation": "databaselookup",
                "configuration": config,
                "blockers": store.get(source["id"]).provenance.get("blockers", []),
            },
        )
        mapping = " UNION ALL ".join(
            f"SELECT {ident(ROW_ID)} row_id, {literal(parent['id'])} parent_id, {column} parent_row_id "
            f"FROM {store.relation(ref['id'])}"
            for parent, column in [(source, "_lookup_input_row_id"), (remote, "_lookup_source_row_id")]
        )
        store.link(ref, mapping, [source["id"], remote["id"]])
        outputs[port] = ref
    return outputs
