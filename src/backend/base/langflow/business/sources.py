# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""External reads and model adapters with explicit schemas and preserved raw evidence."""

import json
from http import HTTPStatus
from uuid import UUID

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from langflow.business.connections import decrypt
from langflow.business.datasets import ROW_ID, ident, json_value, literal, safe_json
from langflow.verification.database import new_id


def original_facts(value):
    """A typed canonical value keeps JSON numbers distinct from numeric-looking strings."""
    from decimal import Decimal

    if isinstance(value, dict):
        return ["object", [[k, original_facts(v)] for k, v in sorted(value.items())]]
    if isinstance(value, list):
        return ["array", [original_facts(v) for v in value]]
    if isinstance(value, Decimal):
        return ["decimal", str(value)]
    return [type(value).__name__, value]


def arrow_schema(fields):
    types = {
        "text": pa.string(),
        "integer": pa.int64(),
        "number": pa.decimal128(38, 6),
        "boolean": pa.bool_(),
        "date": pa.date32(),
        "datetime": pa.timestamp("us", tz="UTC"),
    }
    return pa.schema(
        [
            pa.field(
                f["name"],
                pa.decimal128(f.get("precision", 38), f.get("scale", 6))
                if f["type"] == "number"
                else (pa.timestamp("us", tz=f.get("timezone", "UTC")) if f["type"] == "datetime" else types[f["type"]]),
                nullable=f.get("nullable", True),
            )
            for f in fields
        ]
    )


def path_value(value, path):
    for part in path.split(".") if path else []:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def bindings(value, parameters, record=None):
    if isinstance(value, dict):
        if set(value) == {"parameter"}:
            return parameters[value["parameter"]]
        if set(value) == {"field"}:
            return (record or {})[value["field"]]
        return {k: bindings(v, parameters, record) for k, v in value.items()}
    if isinstance(value, list):
        return [bindings(v, parameters, record) for v in value]
    return value


def client_for(connection, settings):
    url = connection.config["base_url"].rstrip("/")
    token = decrypt(connection.secret, settings)
    headers = (
        {
            connection.config.get("auth_header") or "Authorization": (
                connection.config.get("auth_prefix", "Bearer") + " " + token
            ).lstrip()
        }
        if token
        else {}
    )
    return httpx.Client(base_url=url, headers=headers, timeout=60, follow_redirects=False)


def request(client, method, path, payload):
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        msg = "Request path must be relative to the registered connection"
        raise ValueError(msg)
    response = client.request(
        method, path, **({"params": payload} if method == "GET" else {"json": safe_json(payload)})
    )
    response.raise_for_status()
    from decimal import Decimal

    try:
        payload = response.json(parse_float=Decimal)
    except ValueError as exc:
        from langflow.business.requests import UnreadableResponseError

        raise UnreadableResponseError({"raw_body": response.text, "http_status": response.status_code}) from exc
    if response.status_code == HTTPStatus.ACCEPTED:
        from langflow.business.requests import AcceptedResponseError

        raise AcceptedResponseError(payload)
    return payload


def normalize(row, schema):
    from datetime import date, datetime
    from decimal import Decimal

    result = {}
    for field in schema:
        value = row.get(field.name)
        if value is not None:
            if pa.types.is_decimal(field.type):
                value = Decimal(str(value))
            elif pa.types.is_string(field.type) and not isinstance(value, str):
                value = json.dumps(value, default=json_value, ensure_ascii=False)
            elif pa.types.is_timestamp(field.type) and isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif pa.types.is_date(field.type) and isinstance(value, str):
                value = date.fromisoformat(value)
        result[field.name] = value
    return result


def api_read(store, node, config, connection, settings, parameters, source=None):
    from langflow.business.datasets import IncompleteReadError

    declared = arrow_schema(config["fields"])
    # A rejected value must still fit in the raw snapshot; its original remains in _raw_record.
    schema = pa.schema([pa.field(field.name, field.type) for field in declared])
    if {"_raw_record", "_raw_facts", "_request_row_id", ROW_ID}.intersection(schema.names):
        msg = "API fields use reserved provenance names"
        raise ValueError(msg)
    schema = schema.append(pa.field("_raw_record", pa.string())).append(pa.field("_request_row_id", pa.int64()))
    schema = schema.append(pa.field("_raw_facts", pa.string()))
    if config.get("context_fields"):
        if not source:
            msg = "Context fields require an input dataset"
            raise ValueError(msg)
        input_schema = pq.ParquetFile(store.path(source["id"])).schema_arrow
        for name in config["context_fields"]:
            schema = schema.append(pa.field("_context_" + name, input_schema.field(name).type))
    contract = config.get("completeness", {})
    independent = bool(source and contract.get("scope") == "object" and contract.get("basis"))
    pages = {"count": 0, "mode": config.get("pagination", "none"), "consistency": "observed_pages"}
    issue_schema = pa.schema(
        [
            ("_request_row_id", pa.int64()),
            ("page", pa.int64()),
            ("_issue_reason", pa.string()),
            ("_raw_response", pa.string()),
        ]
    )
    issue_id = new_id()
    issue_writer = pq.ParquetWriter(str(store.path(issue_id)), issue_schema.append(pa.field(ROW_ID, pa.int64())))
    issue_count = 0

    def records():
        if not source:
            yield None
        else:
            for batch in pq.ParquetFile(store.path(source["id"])).iter_batches(batch_size=100):
                yield from batch.to_pylist()

    def batches():
        nonlocal issue_count
        with client_for(connection, settings) as client:
            for record in records():
                payload = bindings(config.get("body", {}), parameters, record)
                seen, page, data = set(), 0, None
                try:
                    for page in range(1, config.get("max_pages", 10000) + 1):
                        data = None
                        if pages["count"] >= config.get("max_calls", 10000):
                            msg = "API call limit reached"
                            raise ValueError(msg)
                        if pages["mode"] == "page":
                            payload[config.get("page_parameter", "page")] = page
                        pages["count"] += 1
                        data = request(client, config.get("method", "GET"), config["path"], payload)
                        for condition in config.get("response_conditions", []):
                            if path_value(data, condition["path"]) != condition["equals"]:
                                msg = "API business response did not satisfy its success contract"
                                raise ValueError(msg)
                        rows = path_value(data, config.get("items_path", ""))
                        if not isinstance(rows, list):
                            msg = "API record path must resolve to an array"
                            raise TypeError(msg)
                        invalid_page = False
                        for offset in range(0, len(rows), 5000):
                            originals = [
                                {
                                    **(row if isinstance(row, dict) else {}),
                                    "_raw_record": json.dumps(
                                        row, default=json_value, ensure_ascii=False, sort_keys=True
                                    ),
                                    "_raw_facts": json.dumps(original_facts(row), ensure_ascii=False),
                                    "_request_row_id": record[ROW_ID] if record else None,
                                    **{"_context_" + name: record[name] for name in config.get("context_fields", [])},
                                }
                                for row in rows[offset : offset + 5000]
                            ]
                            try:
                                if any(not isinstance(row, dict) for row in rows[offset : offset + 5000]):
                                    msg = "API records must be objects"
                                    raise TypeError(msg)
                                from langflow.business.field_schema import validate_record

                                for row in originals:
                                    validate_record(row, config["fields"])
                                batch = [normalize(row, schema) for row in originals]
                                pa.Table.from_pylist(batch, schema=schema)
                            except (ValueError, TypeError, ArithmeticError, pa.ArrowException):
                                invalid_page = True
                                # Preserve every occurrence, even when a declared type rejects its value.
                                # This page's scope is blocked below, so null placeholders never become facts.
                                batch = [
                                    {
                                        **{f.name: None for f in declared},
                                        **{name: row[name] for name in schema.names if name not in declared.names},
                                    }
                                    for row in originals
                                ]
                            yield batch
                        if invalid_page:
                            msg = "API records violate the declared schema; original records were retained"
                            raise ValueError(msg)
                        if contract.get("complete_path") and path_value(data, contract["complete_path"]) is not True:
                            msg = "Source did not confirm completeness"
                            raise ValueError(msg)
                        if pages["mode"] == "none" or not rows:
                            break
                        if pages["mode"] == "cursor":
                            cursor = path_value(data, config.get("cursor_path", "next_cursor"))
                            if cursor is None:
                                break
                            if str(cursor) in seen:
                                msg = "API pagination repeated a cursor"
                                raise ValueError(msg)
                            seen.add(str(cursor))
                            payload[config.get("cursor_parameter", "cursor")] = cursor
                    else:
                        msg = "API page limit reached before exhaustion"
                        raise ValueError(msg)
                except (httpx.HTTPError, ValueError, TypeError, KeyError, ArithmeticError, pa.ArrowException) as exc:
                    failed_response = data
                    if failed_response is None:
                        if isinstance(exc, httpx.HTTPStatusError):
                            failed_response = {"http_status": exc.response.status_code, "raw_body": exc.response.text}
                        elif not isinstance(exc, httpx.HTTPError):
                            failed_response = getattr(exc, "response", None)
                    issue_writer.write_table(
                        pa.Table.from_pylist(
                            [
                                {
                                    "_request_row_id": record[ROW_ID] if record else None,
                                    "page": page,
                                    "_issue_reason": "source_incomplete:" + type(exc).__name__,
                                    "_raw_response": json.dumps(failed_response, default=json_value, ensure_ascii=False)
                                    if failed_response is not None
                                    else None,
                                    ROW_ID: issue_count,
                                }
                            ],
                            schema=issue_writer.schema,
                        )
                    )
                    issue_count += 1
                    if not independent:
                        raise

    try:
        try:
            ref = store.write_batches(
                node,
                batches(),
                schema,
                provenance={
                    "connection_id": connection.id,
                    "query": config,
                    "pagination": pages,
                    "parents": [source["id"]] if source else [],
                    "completeness": {"state": "complete" if contract.get("basis") else "unknown", **contract},
                },
            )
        except IncompleteReadError as exc:
            ref = exc.receipt
    finally:
        issue_writer.close()
    issues = store.register(
        issue_id,
        node,
        "issues",
        provenance={
            "parents": [source["id"]] if source else [],
            "scope": "object" if independent else "range",
            "completeness": {"state": "complete"},
        },
    )
    if issue_count:
        from langflow.business.models import Dataset

        ref["completeness"] = {
            "state": "incomplete",
            "scope": "object" if independent else "range",
            "issues": issues["id"],
        }
        with store.database.sessions.begin() as session:
            row = session.get(Dataset, ref["id"])
            row.provenance = {**row.provenance, "completeness": ref["completeness"]}
    if source:
        store.link(
            issues,
            f"SELECT {ident(ROW_ID)} row_id, {literal(source['id'])} parent_id, "
            f"_request_row_id parent_row_id FROM {store.relation(issues['id'])}",
            [source["id"]],
        )
        # Received evidence is itself a source, and also refers to the requesting object.
        raw_lineage = store.lineage(ref["id"])
        links = store.query(
            node,
            f"SELECT * FROM {raw_lineage} UNION "
            f"SELECT r.{ident(ROW_ID)} row_id, l.source_dataset_id, l.source_row_id "
            f"FROM {store.relation(ref['id'])} r JOIN {store.lineage(source['id'])} l ON r._request_row_id=l.row_id",
            port="lineage",
        )
        from langflow.business.models import Dataset

        with store.database.sessions.begin() as session:
            row = session.get(Dataset, ref["id"])
            row.provenance = {**row.provenance, "lineage": links["id"], "scope_issues": issues["id"]}
    if independent:
        # Only fully read independent scopes proceed. Partial observations remain in the raw snapshot.
        usable = store.query(
            node,
            f"SELECT * FROM {store.relation(ref['id'])} r WHERE NOT EXISTS "
            f"(SELECT 1 FROM {store.relation(issue_id)} e WHERE r._request_row_id=e._request_row_id)",
            parents=[ref["id"]],
            details={"completeness": {"state": "complete", "scope": "successful_objects", "basis": contract["basis"]}},
        )
        store.link(
            usable,
            f"SELECT {ident(ROW_ID)} row_id, {literal(ref['id'])} parent_id, {ident(ROW_ID)} parent_row_id "
            f"FROM {store.relation(usable['id'])}",
            [ref["id"]],
        )
        ref = usable
    return {"data": ref, "issues": issues}


def file_path(owner, file_id):
    from langflow.business.datasets import data_root

    return data_root() / "uploads" / str(UUID(owner)) / str(UUID(file_id))


def file_relation(path, file_format, encoding="utf-8"):
    name = literal(str(path))
    if file_format == "parquet":
        return f"read_parquet({name})"
    if file_format == "csv":
        if encoding.lower() not in {"utf-8", "utf8"}:
            msg = "CSV files must use UTF-8"
            raise ValueError(msg)
        return f"read_csv({name}, header=true, sample_size=-1)"
    if file_format == "json":
        return f"read_json_auto({name}, maximum_object_size=33554432)"
    msg = "Unsupported file format"
    raise ValueError(msg)


def file_read(store, node, config, owner):
    path = file_path(owner, config["file_id"])
    if not path.is_file():
        msg = "File not found"
        raise ValueError(msg)
    relation = file_relation(path, config["format"], config.get("encoding", "utf-8"))
    ref = store.query(
        node,
        f"SELECT *, row_number() OVER ()-1 AS {ident(ROW_ID)} FROM {relation}",
        details={"file_id": config["file_id"], "completeness": {"state": "complete", "basis": "file_exhausted"}},
    )
    from langflow.business.models import Dataset

    with store.database.sessions.begin() as session:
        session.get(Dataset, ref["id"]).raw = True
    from langflow.business.compiler import sql_type

    actual = {f["name"]: f for f in ref["fields"]}
    for field in config.get("fields", []):
        actual_type = sql_type(actual[field["name"]]["type"]) if field["name"] in actual else None
        accepted_types = {sql_type(field["type"])}
        if field["type"] == "number":
            accepted_types.update({"BIGINT", "DOUBLE"})
            if "precision" not in field and actual_type and actual_type.startswith("DECIMAL("):
                accepted_types.add(actual_type)
        elif field["type"] == "datetime":
            accepted_types.add("TIMESTAMP")
        if actual_type not in accepted_types:
            msg = f"File schema differs from the declared field: {field['name']}; refresh metadata or add a transform"
            raise ValueError(msg)
    return ref


MODEL_BATCH_SIZE = 100


def model_read(store, node, config, connection, settings, source, *, port_prefix="", optional_output_fields=()):
    """A synchronous protocol adapter; professional comparability belongs in workflow gates."""
    from langflow.business import requests as ledger

    input_path = store.path(source["id"])
    input_schema = pq.ParquetFile(input_path).schema_arrow
    declared = config["fields"]
    added = arrow_schema(declared)
    collisions = set(input_schema.names) & set(added.names)
    if collisions:
        msg = f"Model output fields already exist: {sorted(collisions)}"
        raise ValueError(msg)
    replaced = {"_issue_reason", "_model_response", "_request_id"}
    schema = pa.schema(
        [
            *[f for f in input_schema if f.name not in replaced],
            *added,
            pa.field("_issue_reason", pa.string()),
            pa.field("_model_response", pa.string()),
            pa.field("_request_id", pa.string()),
        ]
    )
    ids = {port: new_id() for port in ["data", "issues"]}
    schemas = {"data": schema, "issues": pa.schema([pa.field(f.name, f.type, nullable=True) for f in schema])}
    writers = {port: pq.ParquetWriter(str(store.path(dataset_id)), schemas[port]) for port, dataset_id in ids.items()}
    buffers = {port: [] for port in ids}
    calls = 0
    try:
        with client_for(connection, settings) as client:
            for batch in pq.ParquetFile(input_path).iter_batches(batch_size=MODEL_BATCH_SIZE):
                for row in batch.to_pylist():
                    issue, response, parsed, request_id = "", {}, {}, None
                    normalized = {f.name: None for f in added}
                    blocked = ";".join(
                        str(v) for k, v in row.items() if k.endswith(("_blocking_reason", "_issue_reason")) and v
                    )
                    if source.get("completeness", {}).get("state") != "complete":
                        blocked = "source_range_unconfirmed"
                    if blocked:
                        issue = "input_blocked:" + blocked
                    elif calls >= config.get("max_calls", 1000):
                        issue = "call_limit_not_sent"
                    else:
                        record = {f: row[f] for f in config["input_fields"]}
                        payload = {"record": record, "prompt": config.get("prompt", ""), "output_fields": declared}
                        if config.get("body") is not None:
                            payload = bindings(config["body"], {}, row)
                        elif config.get("mode") == "openai":
                            payload = {
                                "model": config["model"],
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": config.get("prompt", "")
                                        + "\nReturn a JSON object with these fields: "
                                        + json.dumps(declared),
                                    },
                                    {"role": "user", "content": json.dumps(safe_json(record))},
                                ],
                                "response_format": {"type": "json_object"},
                            }
                        # Keep persistence outside response-error handling. A failed commit must stop sending.
                        request_id = ledger.prepare(store, node, source, row[ROW_ID], connection, payload)
                        calls += 1
                        try:
                            response = ledger.call(
                                store,
                                request_id,
                                lambda payload=payload: request(
                                    client,
                                    "POST",
                                    config.get("path", "/v1/analyze"),
                                    payload,
                                ),
                            )
                            parsed = (
                                json.loads(response["choices"][0]["message"]["content"])
                                if config.get("mode") == "openai"
                                else response
                            )
                            if not isinstance(parsed, dict) or any(
                                (f["name"] not in parsed and f["name"] not in optional_output_fields)
                                or (parsed.get(f["name"]) is None and not f.get("nullable", True))
                                for f in declared
                            ):
                                issue = "model_output_missing"
                            normalized = normalize(parsed, added)
                            pa.Table.from_pylist([normalized], schema=added)
                        except (httpx.HTTPError, ValueError, TypeError, KeyError, pa.ArrowException) as exc:
                            issue = "model_response_unconfirmed:" + type(exc).__name__
                        ledger.update(store, request_id, validity="invalid" if issue else "valid")
                    buffers["issues" if issue else "data"].append(
                        {
                            **row,
                            **normalized,
                            "_issue_reason": issue,
                            "_request_id": request_id,
                            "_model_response": json.dumps(response, default=json_value, ensure_ascii=False),
                        }
                    )
                    for port, buffered in buffers.items():
                        if len(buffered) >= MODEL_BATCH_SIZE:
                            writers[port].write_table(pa.Table.from_pylist(buffered, schema=schemas[port]))
                            buffered.clear()
            for port, rows in buffers.items():
                if rows:
                    writers[port].write_table(pa.Table.from_pylist(rows, schema=schemas[port]))
    finally:
        for writer in writers.values():
            writer.close()
    outputs = {
        port: store.register(
            dataset_id,
            node,
            port_prefix + port,
            provenance={
                "parents": [source["id"]],
                "connection_id": connection.id,
                "configuration": config,
                "model_calls": calls,
                "completeness": source.get("completeness", {"state": "unknown"}),
            },
        )
        for port, dataset_id in ids.items()
    }
    for ref in outputs.values():
        store.link(
            ref,
            f"SELECT {ident(ROW_ID)} row_id, {literal(source['id'])} parent_id, "
            f"{ident(ROW_ID)} parent_row_id FROM {store.relation(ref['id'])}",
            [source["id"]],
        )
    return outputs
