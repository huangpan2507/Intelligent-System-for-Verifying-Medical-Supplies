# ruff: noqa: S608 - SQL is composed from quoted field names and literals.
"""Collect API records back onto their originating business unit, without multiplying facts."""

from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.sources import api_read


def collection_query(config, source, raw, issues):
    cfg = config["collection"]
    keys = cfg["group_by"]
    retain = list(dict.fromkeys([*keys, *cfg["retain_fields"]]))
    if cfg["output"] in retain or ROW_ID in retain:
        msg = "Collection output must be a new field; row ids are managed automatically"
        raise ValueError(msg)
    address = " || ".join(f"CAST(r.{ident(f)} AS VARCHAR)" for f in cfg["address_fields"])
    valid = " AND ".join(
        f"r.{ident(f)} IS NOT NULL AND CAST(r.{ident(f)} AS VARCHAR)<>''"
        for f in [*cfg["address_fields"], *cfg["item_keys"]]
    )
    facts = "struct_pack(" + ", ".join(f"{ident(f)} := s.{ident(f)}" for f in retain) + ")"
    columns = [f"s.{ident(f)}" if f in keys else f"first(s.{ident(f)}) AS {ident(f)}" for f in retain]
    if cfg.get("item_context"):
        context_output = cfg["output"] + "_context"
        if context_output in retain:
            msg = "Collection context output must be a new field"
            raise ValueError(msg)
        item = (
            "struct_pack(address := "
            + address
            + ", "
            + ", ".join(
                [f"{ident(f)} := s.{ident(f)}" for f in cfg["item_context"]]
                + [f"{ident(f)} := r.{ident(f)}" for f in cfg["item_keys"]]
            )
            + ")"
        )
        columns.append(f"to_json(list(DISTINCT {item}) FILTER (WHERE {valid})) AS {ident(context_output)}")
    reason = (
        f"CASE WHEN count(DISTINCT {facts})>1 THEN 'conflicting_source_facts' "
        "WHEN count(e._request_row_id)>0 THEN 'incomplete_api_request' "
        f"WHEN count(r.{ident(ROW_ID)})=0 THEN 'empty_collection' "
        f"WHEN bool_or(r.{ident(ROW_ID)} IS NOT NULL AND NOT ({valid})) THEN 'invalid_collection_item' "
        "ELSE '' END"
    )
    return (
        f"SELECT {', '.join(columns)}, "
        f"to_json(list(DISTINCT ({address}) ORDER BY ({address})) FILTER (WHERE {valid})) AS {ident(cfg['output'])}, "
        f"{reason} AS _issue_reason, row_number() OVER ()-1 AS {ident(ROW_ID)} "
        f"FROM {source} s LEFT JOIN {raw} r ON s.{ident(ROW_ID)}=r._request_row_id "
        f"LEFT JOIN {issues} e ON s.{ident(ROW_ID)}=e._request_row_id "
        f"GROUP BY {', '.join('s.' + ident(k) for k in keys)}"
    )


def execute(runtime, node, source):
    config, store = node["config"], runtime.store
    node_id = runtime.prefix + node["id"]
    responses = api_read(
        store,
        node_id + "--responses",
        config,
        runtime.connection(config["connection"]),
        runtime.settings,
        runtime.parameters,
        source,
    )
    parents = [source["id"], *(r["id"] for r in responses.values())]
    combined = store.query(
        node_id,
        collection_query(
            config,
            store.relation(source["id"]),
            store.relation(responses["data"]["id"]),
            store.relation(responses["issues"]["id"]),
        ),
        port="collection",
        parents=parents,
    )
    outputs = {}
    for port, op in [("data", "="), ("issues", "<>")]:
        ref = store.query(
            node_id,
            f"SELECT * FROM {store.relation(combined['id'])} WHERE _issue_reason{op}''",
            port=port,
            parents=parents,
            details={
                "operation": "api_collection",
                "configuration": config,
                "blockers": store.get(source["id"]).provenance.get("blockers", []),
            },
        )
        on = " AND ".join(f"g.{ident(k)} IS NOT DISTINCT FROM s.{ident(k)}" for k in config["collection"]["group_by"])
        mapping = (
            f"SELECT g.{ident(ROW_ID)} row_id, {literal(source['id'])} parent_id, s.{ident(ROW_ID)} parent_row_id "
            f"FROM {store.relation(ref['id'])} g JOIN {store.relation(source['id'])} s ON {on}"
        )
        # API evidence also remains reachable through its own request-to-source receipts.
        raw = responses["data"]
        mapping += (
            f" UNION ALL SELECT g.{ident(ROW_ID)}, {literal(raw['id'])}, r.{ident(ROW_ID)} "
            f"FROM {store.relation(ref['id'])} g JOIN {store.relation(source['id'])} s ON {on} "
            f"JOIN {store.relation(raw['id'])} r ON r._request_row_id=s.{ident(ROW_ID)}"
        )
        store.link(ref, mapping, [source["id"], raw["id"]])
        outputs[port] = ref
    return outputs
