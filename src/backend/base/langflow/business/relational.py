# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Pure SQL plans for business-neutral relational nodes."""

from decimal import Decimal

from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.expressions import expression, predicate

MAX_DECIMAL_PRECISION = 38

TYPES = {
    "text": "VARCHAR",
    "integer": "BIGINT",
    "number": "DECIMAL(38,6)",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMPTZ",
}


def fields_of(ref):
    return [f["name"] for f in ref["fields"]]


def identity_queries(config, source, fields, facts):
    """An identity constraint: exact repeats share one fact; contradictory facts all fail."""
    identity = config["identity"]
    keys = identity["keys"]
    if not keys or any(k not in fields for k in keys):
        msg = "Identity requires existing key fields"
        raise ValueError(msg)
    if any(f in fields for f in ["_identity", "_identity_status", "_representative_row_id"]):
        msg = "Identity is already declared; use its existing definition"
        raise ValueError(msg)
    key = "to_json(struct_pack(" + ", ".join(f"{ident(k)} := s.{ident(k)}" for k in keys) + "))"
    missing = " OR ".join(f"s.{ident(k)} IS NULL" for k in keys)
    base = (
        f"SELECT s.*, f.facts AS _identity_facts, CASE WHEN {missing} THEN NULL ELSE "
        f"concat({literal(identity['namespace'] + ':' + identity['name'] + ':')}, {key}) END AS _identity "
        f"FROM {source} s LEFT JOIN ({facts}) f ON s.{ident(ROW_ID)}=f.row_id"
    )
    window = "PARTITION BY _identity"
    ranked = (
        f"SELECT *, count(DISTINCT _identity_facts) OVER ({window}) AS _fact_count, "
        f"min({ident(ROW_ID)}) OVER ({window}) AS _representative_row_id FROM ({base})"
    )
    classified = (
        f"SELECT * EXCLUDE(_fact_count, _identity_facts), CASE WHEN _identity IS NULL THEN 'missing_identity' "
        "WHEN _identity_facts IS NULL THEN 'missing_original_facts' WHEN _fact_count<>1 THEN 'identity_conflict' "
        f"WHEN {ident(ROW_ID)}<>_representative_row_id THEN 'exact_duplicate' ELSE 'canonical' END "
        f"AS _identity_status FROM ({ranked})"
    )
    projected = "* EXCLUDE(_issue_reason)" if "_issue_reason" in fields else "*"
    old_reason = "nullif(_issue_reason, ''), " if "_issue_reason" in fields else ""
    annotated = (
        f"SELECT {projected}, concat_ws(';', {old_reason}CASE WHEN _identity_status NOT IN "
        f"('canonical','exact_duplicate') THEN _identity_status END) AS _issue_reason FROM ({classified})"
    )
    checked_fields = list(
        dict.fromkeys([*fields, "_issue_reason", "_identity", "_identity_status", "_representative_row_id"])
    )
    ordinary = unary_query(
        "validate", {k: v for k, v in config.items() if k != "identity"}, f"({annotated})", checked_fields
    )
    return {
        "valid": f"SELECT * FROM ({ordinary['valid']}) WHERE _identity_status='canonical'",
        "issues": (
            f"{ordinary['issues']} UNION ALL SELECT * REPLACE('info' AS _issue_severity) "
            f"FROM ({ordinary['valid']}) WHERE _identity_status='exact_duplicate'"
        ),
    }


def unary_query(kind, config, source, fields, parameters=None):
    if kind == "compare" and config.get("calculations"):
        # Calculations are evaluated in order; later comparisons can bind their outputs.
        for item in config["calculations"]:
            source = "(" + unary_query("transform", {"transforms": [item]}, source, fields, parameters)["data"] + ")"
            fields = list(dict.fromkeys([*fields, item["output"]]))
    if kind == "transform":
        selected = config.get("select") or [f for f in fields if f != ROW_ID]
        for f in selected:
            if f not in fields:
                msg = f"Unknown field: {f}"
                raise ValueError(msg)
        values = {f: ident(f) for f in selected}
        issues = [f"nullif({ident(f)}, '')" for f in fields if f.endswith("_issue_reason")]
        for item in config.get("transforms", []):
            name = item["output"]
            if name == ROW_ID:
                msg = "Reserved output field"
                raise ValueError(msg)
            method = item.get("operation", "copy")
            source_field = item.get("field", "")
            if method != "expression" and source_field not in fields:
                msg = f"Unknown field: {source_field}"
                raise ValueError(msg)
            sql = ident(source_field)
            if method == "cast":
                target = TYPES[item["type"]]
                if item["type"] == "number":
                    precision, scale = item.get("precision", 38), item.get("scale", 6)
                    if not 0 <= scale <= precision <= MAX_DECIMAL_PRECISION:
                        msg_0 = "Decimal scale must be between zero and precision (at most 38)"
                        raise ValueError(msg_0)
                    target = f"DECIMAL({precision},{scale})"
                    sql = (
                        f"CASE WHEN business_decimal_fits(CAST({sql} AS VARCHAR), {precision}, {scale}) "
                        f"THEN TRY_CAST({sql} AS {target}) END"
                    )
                else:
                    sql = f"TRY_CAST({sql} AS {target})"
                issues.append(
                    f"CASE WHEN {ident(source_field)} IS NOT NULL AND ({sql}) IS NULL "
                    f"THEN {literal('conversion:' + name)} END"
                )
            elif method == "map":
                mapping = item.get("mapping", {})
                sql = (
                    "CASE "
                    + " ".join(
                        f"WHEN CAST({ident(source_field)} AS VARCHAR)={literal(k)} THEN {literal(v)}"
                        for k, v in mapping.items()
                    )
                    + " ELSE NULL END"
                )
            elif method == "expression":
                sql = expression(item["expression"], fields)
            elif method != "copy":
                msg = f"Unsupported transform: {method}"
                raise ValueError(msg)
            values[name] = sql
        if issues:
            values["_issue_reason"] = "concat_ws(';', " + ", ".join(issues) + ")"
        columns = [f"{sql} AS {ident(name)}" for name, sql in values.items()]
        return {"data": f"SELECT {', '.join(columns)}, {ident(ROW_ID)} FROM {source}"}
    if kind == "filter":
        where = predicate(config, fields, parameters)
        return {
            port: f"SELECT * FROM {source} WHERE ({where}) IS {state}"
            for port, state in [("matched", "TRUE"), ("unmatched", "FALSE"), ("unknown", "NULL")]
        }
    if kind == "validate":
        checks = []
        for f in config.get("required", []):
            if f not in fields:
                msg = f"Unknown required field: {f}"
                raise ValueError(msg)
            checks.append((f"{ident(f)} IS NULL", f"required:{f}"))
        keys = config.get("unique", [])
        if keys:
            if any(k not in fields for k in keys):
                msg = "Unknown unique-key field"
                raise ValueError(msg)
            checks.append((f"count(*) OVER (PARTITION BY {', '.join(ident(k) for k in keys)}) > 1", "duplicate_key"))
        checks.extend(
            (f"({predicate({'conditions': [item]}, fields, parameters)}) IS NOT TRUE", f"condition:{item['field']}")
            for item in config.get("conditions", [])
        )
        reasons = (["nullif(_issue_reason, '')"] if "_issue_reason" in fields else []) + [
            f"CASE WHEN {sql} THEN {literal(label)} END" for sql, label in checks
        ]
        reason = "concat_ws(';', " + ", ".join(reasons) + ")" if reasons else "''"
        replaced = [name for name in ["_issue_reason", "_issue_severity"] if name in fields]
        projection = "* EXCLUDE(" + ", ".join(replaced) + ")" if replaced else "*"
        query = f"SELECT {projection}, {reason} AS _issue_reason FROM {source}"
        return {
            "valid": f"SELECT *, '' AS _issue_severity FROM ({query}) WHERE _issue_reason=''",
            "issues": f"SELECT *, 'error' AS _issue_severity FROM ({query}) WHERE _issue_reason<>''",
        }
    if kind == "aggregate":
        groups = config.get("group_by", [])
        if any(k not in fields for k in groups):
            msg = "Unknown grouping field"
            raise ValueError(msg)
        metrics = []
        for item in config.get("metrics", []):
            op = item["operation"]
            if op not in {"sum", "count", "min", "max", "avg", "collect"}:
                msg = "Unsupported aggregation"
                raise ValueError(msg)
            field = item.get("field")
            if field and field not in fields:
                msg = f"Unknown metric field: {field}"
                raise ValueError(msg)
            value = (
                f"to_json(list({ident(field)} ORDER BY {ident(field)}))"
                if op == "collect"
                else f"{op}({ident(field) if field else '*'})"
            )
            metrics.append(f"{value} AS {ident(item['output'])}")
        if not metrics:
            msg = "At least one aggregate metric is required"
            raise ValueError(msg)
        invalid = [
            f"{ident(i['field'])} IS NULL" for i in config["metrics"] if i.get("field") and i["operation"] != "count"
        ]
        invalid += [
            f"nullif({ident(f)}, '') IS NOT NULL" for f in fields if f.endswith(("_issue_reason", "_blocking_reason"))
        ]
        blocking = " OR ".join(invalid) or "FALSE"
        columns = (
            [ident(g) for g in groups]
            + metrics
            + [f"CASE WHEN bool_or({blocking}) THEN 'invalid_member' ELSE '' END AS _blocking_reason"]
        )
        grouped = f"SELECT {', '.join(columns)} FROM {source}" + (
            f" GROUP BY {', '.join(ident(g) for g in groups)}" if groups else ""
        )
        return {"data": f"SELECT *, row_number() OVER () - 1 AS {ident(ROW_ID)} FROM ({grouped})"}
    if kind == "compare":
        checks, deltas = [], []
        blockers = [
            f"nullif({ident(f)}, '') IS NOT NULL"
            for f in fields
            if f.endswith(("_blocking_reason", "_issue_reason")) or f == "_dependency_block"
        ]
        blocked = "WHEN " + " OR ".join(blockers) + " THEN 'unknown' " if blockers else ""
        for index, item in enumerate(config.get("comparisons", [])):
            left, right = item["left"], item["right"]
            if left not in fields or right not in fields:
                msg = f"Comparison field does not exist: {left}, {right}"
                raise ValueError(msg)
            a, b = ident(left), ident(right)
            mode = item.get("mode", "exact")
            eq = f"{a}={b}"
            if mode == "numeric":
                tolerance = str(abs(Decimal(str(item.get("tolerance", 0)))))
                eq = f"abs({a}-{b}) <= {tolerance}"
                deltas.append(f"({b}-{a}) AS {ident('difference_' + str(index))}")
            elif mode == "case_insensitive":
                eq = f"lower({a})=lower({b})"
            elif mode != "exact":
                msg = "Unsupported comparison mode"
                raise ValueError(msg)
            null_equal = item.get("null_equal", False)
            both_null = f"WHEN {a} IS NULL AND {b} IS NULL THEN 'equal'" if null_equal else ""
            checks.append(
                f"CASE {blocked}{both_null} WHEN {a} IS NULL OR {b} IS NULL THEN 'unknown' "
                f"WHEN {eq} THEN 'equal' ELSE 'different' END AS comparison_{index}"
            )
        if not checks:
            msg = "At least one field pair is required"
            raise ValueError(msg)
        replaced = {
            "_comparison_status",
            *[f"comparison_{i}" for i in range(len(checks))],
            *[f"difference_{i}" for i in range(len(checks))],
        } & set(fields)
        projection = "* EXCLUDE(" + ", ".join(ident(f) for f in sorted(replaced)) + ")" if replaced else "*"
        base = f"SELECT {projection}, {', '.join(checks + deltas)} FROM {source}"
        unknown = " OR ".join(f"comparison_{i}='unknown'" for i in range(len(checks)))
        different = " OR ".join(f"comparison_{i}='different'" for i in range(len(checks)))
        missing = "WHEN _match_status<>'matched' THEN _match_status" if "_match_status" in fields else ""
        aliases = [(i, item["output"]) for i, item in enumerate(config["comparisons"]) if item.get("output")]
        if len({name for _, name in aliases}) != len(aliases) or any(
            name in fields or name.startswith(("_", "comparison_", "difference_")) for _, name in aliases
        ):
            msg = "Comparison result names must be distinct new business fields"
            raise ValueError(msg)
        named = "".join(f", comparison_{i} AS {ident(name)}" for i, name in aliases)
        return {
            "data": (
                f"SELECT *{named}, CASE {missing} WHEN {unknown} THEN 'unknown' "
                f"WHEN {different} THEN 'different' ELSE 'equal' END AS _comparison_status FROM ({base})"
            )
        }
    if kind == "output":
        selected = config.get("columns") or [f for f in fields if f != ROW_ID]
        if any(f not in fields for f in selected):
            msg = "Result field does not exist"
            raise ValueError(msg)
        selected = list(dict.fromkeys([*selected, ROW_ID]))
        return {"data": f"SELECT {', '.join(ident(f) for f in selected)} FROM {source}"}
    msg = f"Unknown unary operation: {kind}"
    raise ValueError(msg)


def join_queries(config, left, right, left_fields, right_fields):
    keys = config.get("keys", [])
    if not keys:
        msg = "Join keys are required; row-position matching is not supported"
        raise ValueError(msg)
    for pair in keys:
        if pair["left"] not in left_fields or pair["right"] not in right_fields:
            msg = "Join key does not exist"
            raise ValueError(msg)
    mode = config.get("cardinality", "one_to_one")
    if mode not in {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}:
        msg = "Invalid join cardinality"
        raise ValueError(msg)

    def checked(source, side, unique):
        names = [ident(k[side]) for k in keys]
        invalid = " OR ".join(f"{n} IS NULL" for n in names)
        if unique:
            invalid += f" OR count(*) OVER (PARTITION BY {', '.join(names)})>1"
        return f"SELECT *, ({invalid}) AS _key_invalid FROM {source}"

    left_checked = checked(left, "left", mode in {"one_to_one", "one_to_many"})
    right_checked = checked(right, "right", mode in {"one_to_one", "many_to_one"})
    on = " AND ".join(f"l.{ident(k['left'])}=r.{ident(k['right'])}" for k in keys)
    how = {"full": "FULL OUTER", "left": "LEFT", "inner": "INNER", "right": "RIGHT"}[config.get("how", "full")]
    cols = [f"l.{ident(f)} AS {ident('left_' + f)}" for f in left_fields]
    cols += [f"r.{ident(f)} AS {ident('right_' + f)}" for f in right_fields]
    # Do not emit a valid counterpart as a misleading single-sided result when its key is ambiguous on the other side.
    left_valid = (
        f"SELECT * FROM ({left_checked}) l WHERE NOT _key_invalid AND NOT EXISTS("
        f"SELECT 1 FROM ({right_checked}) r WHERE _key_invalid AND {on})"
    )
    right_valid = (
        f"SELECT * FROM ({right_checked}) r WHERE NOT _key_invalid AND NOT EXISTS("
        f"SELECT 1 FROM ({left_checked}) l WHERE _key_invalid AND {on})"
    )
    status = (
        f"CASE WHEN l.{ident(ROW_ID)} IS NULL THEN 'right_only' "
        f"WHEN r.{ident(ROW_ID)} IS NULL THEN 'left_only' ELSE 'matched' END"
    )
    data = (
        f"SELECT {', '.join(cols)}, {status} AS _match_status, row_number() OVER ()-1 AS {ident(ROW_ID)} "
        f"FROM ({left_valid}) l {how} JOIN ({right_valid}) r ON {on}"
    )
    left_exclude = "_key_invalid, _issue_reason" if "_issue_reason" in left_fields else "_key_invalid"
    right_exclude = "_key_invalid, _issue_reason" if "_issue_reason" in right_fields else "_key_invalid"
    issue_left = (
        f"SELECT * EXCLUDE({left_exclude}), 'left' AS _issue_side, "
        f"'ambiguous_or_missing_join_key' AS _issue_reason FROM ({left_checked}) l "
        f"WHERE _key_invalid OR EXISTS(SELECT 1 FROM ({right_checked}) r WHERE _key_invalid AND {on})"
    )
    issue_right = (
        f"SELECT * EXCLUDE({right_exclude}), 'right' AS _issue_side, "
        f"'ambiguous_or_missing_join_key' AS _issue_reason FROM ({right_checked}) r "
        f"WHERE _key_invalid OR EXISTS(SELECT 1 FROM ({left_checked}) l WHERE _key_invalid AND {on})"
    )
    issues = (
        f"SELECT * EXCLUDE({ident(ROW_ID)}), {ident(ROW_ID)} AS _join_source_row_id, "
        f"row_number() OVER ()-1 AS {ident(ROW_ID)} FROM (({issue_left}) UNION ALL BY NAME ({issue_right}))"
    )
    return {"data": data, "issues": issues}
