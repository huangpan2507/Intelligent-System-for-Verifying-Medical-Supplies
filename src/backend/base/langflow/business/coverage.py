# ruff: noqa: S608 - SQL values and identifiers use the shared quoting functions.
"""One final audit of declared obligations, independent of business labels and output timing."""

from sqlalchemy import select

from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.models import Dataset, TaskAssessment


def declaration(graph, schemas):
    nodes = {n["id"]: n for n in graph["nodes"]}
    declarations = [n for n in nodes.values() if n["config"].get("obligation")]
    if not declarations:
        return {"mode": "ordinary"}
    if len(declarations) != 1 or declarations[0]["kind"] != "output" or not declarations[0]["config"].get("primary"):
        msg = "Declare the result obligation once, on the primary Output"
        raise ValueError(msg)
    contract = declarations[0]["config"]["obligation"]
    if contract["mode"] == "ordinary":
        return contract
    if not contract.get("sources") or not contract.get("checks"):
        msg = "Verification requires original sources, identities and checks"
        raise ValueError(msg)
    names = [c["name"] for c in contract["checks"]]
    if len(names) != len(set(names)):
        msg = "Check names must be unique"
        raise ValueError(msg)
    source_names = [s["node"] for s in contract["sources"]]
    if len(source_names) != len(set(source_names)):
        msg = "Original sources must be unique"
        raise ValueError(msg)
    for source in contract["sources"]:
        origin, identity = nodes.get(source["node"]), nodes.get(source["identity"])
        if not origin or origin["kind"] not in {"database", "api", "file"}:
            msg = "Coverage source must be an original read node"
            raise ValueError(msg)
        if not identity or identity["kind"] != "validate" or not identity["config"].get("identity"):
            msg = "Coverage must reference an identity declared in Validate"
            raise ValueError(msg)
        ancestors, frontier = set(), [identity["id"]]
        while frontier:
            target = frontier.pop()
            for edge in graph["edges"]:
                if edge["target"] == target and edge["source"] not in ancestors:
                    ancestors.add(edge["source"])
                    frontier.append(edge["source"])
        if origin["id"] not in ancestors:
            msg = "Coverage identity does not descend from the declared source"
            raise ValueError(msg)
    references = [*contract.get("dispositions", [])]
    for check in contract["checks"]:
        references += [check["units"], *check["results"]]
    for ref in references:
        fields = schemas.get(ref["node"], {}).get(ref["port"])
        if fields is None:
            msg = f"Unknown result reference: {ref['node']}.{ref['port']}"
            raise ValueError(msg)
        available = {f["name"] for f in fields}
        for key in ["status_field", "reason_field", "evidence_field"]:
            if ref.get(key) and ref[key] not in available:
                msg = f"Unknown result field: {ref[key]}"
                raise ValueError(msg)
    for spec in contract.get("dispositions", []):
        if bool(spec.get("status")) == bool(spec.get("status_field")):
            msg = "Each disposition needs exactly one status or status field"
            raise ValueError(msg)
        if bool(spec.get("reason")) == bool(spec.get("reason_field")):
            msg = "Each disposition needs exactly one reason or reason field"
            raise ValueError(msg)
    for check in contract["checks"]:
        for result in check["results"]:
            if bool(result.get("status")) == bool(result.get("status_field")):
                msg = "Each check result needs exactly one status or status field"
                raise ValueError(msg)
    return contract


def finalize(runtime):
    """Called once after all graph branches terminate, including a failed execution."""
    store = runtime.store
    with store.database.sessions() as session:
        datasets = list(session.scalars(select(Dataset).where(Dataset.task_id == store.task_id)))
    sources = [
        {
            "node": d.node_id,
            "dataset_id": d.id,
            "received_rows": d.row_count,
            **d.provenance.get("completeness", {"state": "unknown"}),
        }
        for d in datasets
        if d.raw
    ]
    contract = runtime.package.get("obligation", {"mode": "ordinary"})
    summary = {
        "mode": contract["mode"],
        "sources": sources,
        "execution_errors": runtime.failures,
        "state": "not_required",
        "checks": [],
    }
    if contract["mode"] == "verification":
        summary.update(audit(runtime, contract, datasets))
    with store.database.sessions.begin() as session:
        session.merge(TaskAssessment(task_id=store.task_id, summary=summary))
    return summary


def audit(runtime, contract, datasets):
    store = runtime.store

    def reference(spec):
        return runtime.outputs.get(spec["node"], {}).get(spec["port"])

    origins = [d for d in datasets if d.raw and d.node_id in {s["node"] for s in contract["sources"]}]
    source_ids = [d.id for d in origins]
    allowed = ",".join(literal(i) for i in source_ids) or "NULL"
    original = (
        " UNION ALL ".join(
            f"SELECT {literal(d.id)} source_dataset_id, {ident(ROW_ID)} source_row_id FROM {store.relation(d.id)}"
            for d in origins
        )
        or "SELECT NULL::VARCHAR source_dataset_id, NULL::BIGINT source_row_id WHERE FALSE"
    )
    identity_parts = []
    for source in contract["sources"]:
        for port in ["valid", "issues"]:
            ref = reference({"node": source["identity"], "port": port})
            if ref and "_identity" in {f["name"] for f in ref["fields"]}:
                identity_parts.append(
                    f"SELECT l.source_dataset_id, l.source_row_id, r._identity FROM {store.lineage(ref['id'])} l "
                    f"JOIN {store.relation(ref['id'])} r ON l.row_id=r.{ident(ROW_ID)} "
                    f"WHERE l.source_dataset_id IN ({allowed})"
                )
    identity = (
        " UNION ".join(identity_parts)
        or "SELECT NULL::VARCHAR source_dataset_id, NULL::BIGINT source_row_id, NULL::VARCHAR _identity WHERE FALSE"
    )
    unit_records, dispositions, statistics = [], [], []
    for check in contract["checks"]:
        units = reference(check["units"])
        if not units:
            statistics.append({"name": check["name"], "state": "not_executed", "units": 0})
            continue
        answers, fallbacks = [], []
        for result in check["results"]:
            ref = reference(result)
            if not ref:
                continue
            status = (
                f"CAST(r.{ident(result['status_field'])} AS VARCHAR)"
                if result.get("status_field")
                else literal(result["status"])
            )
            reason = (
                f"CAST(r.{ident(result['reason_field'])} AS VARCHAR)"
                if result.get("reason_field")
                else literal(result.get("reason", ""))
            )
            evidence = (
                f"CAST(r.{ident(result['evidence_field'])} AS VARCHAR)"
                if result.get("evidence_field")
                else "NULL::VARCHAR"
            )
            (fallbacks if result.get("fallback") else answers).append(
                f"SELECT DISTINCT u.row_id unit_row_id, {status} status, {reason} reason, {evidence} evidence, "
                f"{literal(ref['id'])} result_dataset_id, r.{ident(ROW_ID)} result_row_id "
                f"FROM {store.lineage(units['id'])} u JOIN {store.lineage(ref['id'])} l "
                "ON u.source_dataset_id=l.source_dataset_id AND u.source_row_id=l.source_row_id "
                f"JOIN {store.relation(ref['id'])} r ON r.{ident(ROW_ID)}=l.row_id WHERE "
                f"u.source_dataset_id IN ({allowed})"
            )
        observations = " UNION ALL ".join(answers) or (
            "SELECT NULL::BIGINT unit_row_id, NULL::VARCHAR status, NULL::VARCHAR reason, "
            "NULL::VARCHAR evidence, NULL::VARCHAR result_dataset_id, NULL::BIGINT result_row_id WHERE FALSE"
        )
        if fallbacks:
            observations = (
                f"WITH primary_answers AS ({observations}), fallback_answers AS ({' UNION ALL '.join(fallbacks)}) "
                "SELECT * FROM primary_answers UNION ALL SELECT f.* FROM fallback_answers f "
                "WHERE NOT EXISTS (SELECT 1 FROM primary_answers p WHERE p.unit_row_id=f.unit_row_id)"
            )
        # Identical terminal answers count once. Conflicting answers never choose the last row.
        query = (
            f"WITH answers AS ({observations}), summary AS (SELECT unit_row_id, count(DISTINCT status) variants, "
            "min(status) status, string_agg(DISTINCT nullif(reason,''), ';') reason, "
            "string_agg(DISTINCT evidence, ';') evidence, to_json(list(DISTINCT "
            "struct_pack(dataset_id := result_dataset_id, row_id := result_row_id))) "
            "result_refs "
            "FROM answers GROUP BY unit_row_id) "
            f"SELECT u.{ident(ROW_ID)} AS {ident(ROW_ID)}, {literal(units['id'])} unit_dataset_id, "
            f"u.{ident(ROW_ID)} unit_row_id, {literal(check['name'])} check_name, "
            "CASE WHEN s.variants>1 THEN 'result_conflict' WHEN s.status IN "
            "('equal','different','not_applicable') THEN s.status ELSE 'uncompared' END "
            "status, "
            "CASE WHEN s.variants>1 THEN 'contradictory_results' WHEN s.variants IS NULL THEN 'missing_result' "
            "ELSE coalesce(nullif(s.reason,''), CASE WHEN s.status NOT IN "
            "('equal','different','not_applicable') THEN "
            "coalesce(s.status,'unknown_status') ELSE '' END) END reason, "
            "s.evidence, s.result_refs, (s.variants IS NULL OR s.variants>1) coverage_gap "
            f"FROM {store.relation(units['id'])} u LEFT JOIN summary s ON s.unit_row_id=u.{ident(ROW_ID)}"
        )
        receipt = store.query("Assessment", query, port="unit_results", parents=[units["id"]], name=check["name"])
        store.link(
            receipt,
            f"SELECT {ident(ROW_ID)} row_id, {literal(units['id'])} parent_id, unit_row_id parent_row_id "
            f"FROM {store.relation(receipt['id'])}",
            [units["id"]],
        )
        unit_records.append(receipt["id"])
        dispositions.append(
            f"SELECT l.source_dataset_id, l.source_row_id, r.status, r.reason, r.coverage_gap "
            f"FROM {store.lineage(receipt['id'])} l JOIN {store.relation(receipt['id'])} "
            f"r ON l.row_id=r.{ident(ROW_ID)}"
        )
        with store.engine() as db:
            counts = dict(
                db.execute(f"SELECT status, count(*) FROM {store.relation(receipt['id'])} GROUP BY status").fetchall()
            )
            gaps = db.execute(f"SELECT count(*) FROM {store.relation(receipt['id'])} WHERE coverage_gap").fetchone()[0]
        statistics.append(
            {
                "name": check["name"],
                "units": receipt["row_count"],
                "counts": counts,
                "effective": counts.get("equal", 0) + counts.get("different", 0),
                "coverage_gaps": gaps,
                "dataset_id": receipt["id"],
            }
        )
    for spec in contract.get("dispositions", []):
        ref = reference(spec)
        if ref:
            status = (
                f"CAST(r.{ident(spec['status_field'])} AS VARCHAR)"
                if spec.get("status_field")
                else literal(spec["status"])
            )
            reason = (
                f"CAST(r.{ident(spec['reason_field'])} AS VARCHAR)"
                if spec.get("reason_field")
                else literal(spec["reason"])
            )
            valid = f"coalesce({status} IN ('excluded','uncompared','issue'), FALSE)"
            dispositions.append(
                f"SELECT l.source_dataset_id, l.source_row_id, CASE WHEN {valid} THEN {status} "
                f"ELSE 'uncompared' END status, {reason} reason, NOT ({valid}) coverage_gap "
                f"FROM {store.lineage(ref['id'])} l JOIN {store.relation(ref['id'])} r ON l.row_id=r.{ident(ROW_ID)}"
            )
    outcomes = " UNION ALL ".join(dispositions) or (
        "SELECT NULL::VARCHAR source_dataset_id, NULL::BIGINT source_row_id, NULL::VARCHAR status, "
        "NULL::VARCHAR reason, FALSE coverage_gap WHERE FALSE"
    )
    disposition_query = (
        f"WITH original AS ({original}), identities AS ({identity}), outcomes AS ({outcomes}), "
        "o AS (SELECT source_dataset_id, source_row_id, string_agg(DISTINCT status, ';' ORDER BY status) status, "
        "string_agg(DISTINCT nullif(reason,''), ';') reason, bool_or(coverage_gap) "
        "coverage_gap FROM outcomes GROUP BY ALL), "
        "i AS (SELECT source_dataset_id, source_row_id, min(_identity) business_identity FROM identities GROUP BY ALL) "
        "SELECT original.*, i.business_identity, coalesce(o.status,'coverage_gap') status, "
        "coalesce(o.reason, CASE WHEN o.status IS NULL THEN 'no_declared_disposition' ELSE '' END) reason, "
        "coalesce(o.coverage_gap, TRUE) coverage_gap, row_number() OVER ()-1 AS _business_row_id "
        "FROM original LEFT JOIN o USING(source_dataset_id, source_row_id) LEFT JOIN i "
        "USING(source_dataset_id, source_row_id)"
    )
    detail = store.query(
        "Assessment", disposition_query, port="dispositions", parents=source_ids, name="Original record dispositions"
    )
    with store.engine() as db:
        known, identities, missing, gaps = db.execute(
            f"SELECT count(*), count(DISTINCT business_identity), count(*) FILTER(WHERE business_identity IS NULL), "
            f"count(*) FILTER(WHERE coverage_gap) FROM {store.relation(detail['id'])}"
        ).fetchone()
    discovered = len({d.node_id for d in origins}) == len(contract["sources"]) and all(
        d.provenance.get("completeness", {}).get("state") == "complete" for d in origins
    )
    runtime.output_ids = [detail["id"], *unit_records, *runtime.output_ids]
    return {
        "state": "gaps" if gaps or any(c.get("state") == "not_executed" for c in statistics) else "accounted",
        "discovery_complete": discovered,
        "received_records": known,
        "business_identities": identities,
        "missing_identity_records": missing,
        "coverage_gap_records": gaps,
        "known_record_accountability": (known - gaps) / known if known else None,
        "dispositions_dataset_id": detail["id"],
        "checks": statistics,
    }
