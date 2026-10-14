"""Source field evidence, bounded discovery and configuration-time reference checks."""

import json
from copy import deepcopy
from decimal import Decimal
from http import HTTPStatus

import jsonschema
from cryptography.fernet import InvalidToken

from langflow.business.connections import cipher
from langflow.business.datasets import safe_json


def source_spec(config):
    """Bind evidence to the source request, not to its editable downstream projection."""
    if config.get("sql"):
        return deepcopy({key: config.get(key) for key in ("connection", "sql", "parameters")})
    return deepcopy(
        {
            "connection": config.get("connection"),
            "path": config.get("path"),
            "method": config.get("method", "GET"),
            "body": config.get("body", {}),
            "items_path": config.get("items_path", ""),
            "response_conditions": config.get("response_conditions", []),
        }
    )


def check_fields(fields):
    from langflow.business.catalog import SCHEMA_FIELDS

    jsonschema.validate(fields, SCHEMA_FIELDS)
    names = [field["name"] for field in fields]
    reserved = {"_business_row_id", "_raw_record", "_raw_facts", "_request_row_id", "_blocking_reason"}
    if (
        not names
        or len(set(names)) != len(names)
        or any(not name.strip() or name in reserved or name.startswith("_context_") for name in names)
    ):
        msg = "Source fields must have unique nonempty names outside the reserved provenance namespace"
        raise ValueError(msg)


def document_evidence(config, fields, reference):
    check_fields(fields)
    if not isinstance(reference, str) or not reference.strip():
        msg = "Provide the source document and version for this field contract"
        raise ValueError(msg)
    return {
        "kind": "document",
        "reference": reference.strip(),
        "source": source_spec(config),
        "fields": deepcopy(fields),
    }


def sample_evidence(config, fields, connection, settings, owner):
    evidence = {
        "kind": "sql" if config.get("sql") else "sample",
        "source": source_spec(config),
        "fields": fields,
        "owner": owner,
        "revision": connection.revision,
    }
    return {**evidence, "proof": cipher(settings).encrypt(json.dumps(evidence, sort_keys=True).encode()).decode()}


def validate_evidence(config, connection, settings, owner):
    fields = config.get("fields", [])
    check_fields(fields)
    evidence = config.get("field_evidence") or {}
    if evidence.get("source") != source_spec(config):
        msg = "Source fields are unverified or the source changed; discover fields or apply its document contract again"
        raise ValueError(msg)
    if evidence.get("kind") == "document" and not config.get("sql"):
        document_evidence(config, evidence.get("fields", []), evidence.get("reference"))
        available = {f["name"]: f for f in evidence["fields"]}
        if any(available.get(f["name"]) != f for f in fields):
            msg = "Field definitions differ from their document evidence; update the source contract explicitly"
            raise ValueError(msg)
        return
    if evidence.get("kind") not in {"sample", "sql"} or bool(config.get("sql")) != (evidence["kind"] == "sql"):
        msg = "Use a source document contract or an actual preview as field evidence"
        raise ValueError(msg)
    try:
        proof = evidence.get("proof", "")
        if not isinstance(proof, str):
            raise TypeError
        verified = json.loads(cipher(settings).decrypt(proof.encode()))
    except (InvalidToken, ValueError, TypeError) as exc:
        msg = "Invalid field discovery proof; repeat the preview"
        raise ValueError(msg) from exc
    if (
        verified != {k: v for k, v in evidence.items() if k != "proof"}
        or verified.get("owner") != owner
        or verified.get("revision") != connection.revision
    ):
        msg = "Field discovery proof does not match this source or owner; repeat the preview"
        raise ValueError(msg)
    names = [f["name"] for f in fields]
    observed = [f["name"] for f in evidence["fields"]]
    if (config.get("sql") and names != observed) or not set(names).issubset(observed):
        msg = "Selected fields were not observed in this discovery evidence"
        raise ValueError(msg)


def validate_record(row, fields):
    """Presence and nullability are separate; optional absent properties remain unknown."""
    for field in fields:
        name = field["name"]
        if name not in row:
            if field.get("required", True):
                msg = f"Required API property is absent: {name}"
                raise ValueError(msg)
        elif row[name] is None and not field.get("nullable", True):
            msg = f"API property cannot be null: {name}"
            raise ValueError(msg)


def validate_references(value, schema, available, outputs, path="configuration"):
    """Use the same field annotations as the UI, including dataset-specific references."""
    if schema.get("format", "").startswith("field") and value not in (None, ""):
        port = schema["format"].partition(":")[2] or "data"
        if value not in {f["name"] for f in available.get(port, [])}:
            msg = f"Unavailable field at {path}: {value} (input {port})"
            raise ValueError(msg)
    if isinstance(value, dict) and schema.get("properties"):
        if isinstance(value.get("node"), str):
            available = {"data": outputs.get(value["node"], {}).get(value.get("port", "data"), [])}
        for key, child in schema["properties"].items():
            # Coverage validates cross-branch result references after every output is known.
            if key == "obligation":
                continue
            if key in value:
                validate_references(value[key], child, available, outputs, f"{path}.{key}")
    elif isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            validate_references(item, schema["items"], available, outputs, f"{path}[{index}]")


def validate_bindings(value, fields, parameters):
    if isinstance(value, dict):
        if set(value) == {"field"} and value["field"] not in {f["name"] for f in fields}:
            msg = f"Unavailable request field: {value['field']}"
            raise ValueError(msg)
        if set(value) == {"parameter"} and value["parameter"] not in parameters:
            msg = f"Unknown task parameter: {value['parameter']}"
            raise ValueError(msg)
        for child in value.values():
            validate_bindings(child, fields, parameters)
    elif isinstance(value, list):
        for child in value:
            validate_bindings(child, fields, parameters)


def fields_from_schema(document, config):
    """Import JSON Schema response documents or OpenAPI JSON with local references only."""

    def resolve(value, seen=()):
        if not isinstance(value, dict):
            msg = "Expected a JSON Schema object"
            raise TypeError(msg)
        if "$ref" not in value:
            return value
        ref = value["$ref"]
        if not ref.startswith("#/") or ref in seen:
            msg = "Only nonrecursive local schema references are supported"
            raise ValueError(msg)
        target = document
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return resolve(target, (*seen, ref))

    schema = document
    if "openapi" in document:
        responses = document["paths"][config["path"]][config.get("method", "GET").lower()]["responses"]
        choices = [key for key in responses if str(key).startswith("2")]
        if len(choices) != 1:
            msg = "Import a response JSON Schema when an operation has multiple success responses"
            raise ValueError(msg)
        response = resolve(responses[choices[0]])
        schema = response["content"]["application/json"]["schema"]
    for part in config.get("items_path", "").split(".") if config.get("items_path") else []:
        schema = resolve(schema)["properties"][part]
    schema = resolve(schema)
    if schema.get("type") != "array":
        msg = "The response record path must describe an array"
        raise ValueError(msg)
    record = resolve(schema["items"])
    fields = []
    for name, definition in record.get("properties", {}).items():
        item = resolve(definition)
        kind = item.get("type")
        nullable = item.get("nullable", False)
        if isinstance(kind, list):
            nullable = "null" in kind
            kinds = [t for t in kind if t != "null"]
            kind = kinds[0] if len(kinds) == 1 else None
        if kind not in {"string", "integer", "number", "boolean"} or any(
            k in item for k in ("oneOf", "anyOf", "allOf")
        ):
            msg = f"Unsupported or ambiguous property {name}; supply an explicit flat record contract"
            raise ValueError(msg)
        field_type = {"string": "text", "integer": "integer", "number": "number", "boolean": "boolean"}[kind]
        if kind == "string" and item.get("format") in {"date", "date-time"}:
            field_type = "date" if item["format"] == "date" else "datetime"
        fields.append(
            {"name": name, "type": field_type, "required": name in record.get("required", []), "nullable": nullable}
        )
    check_fields(fields)
    return fields


def api_preview(connection, settings, config, parameters, record, owner):
    """One bounded request; never page, execute predecessors, or create a business task."""
    from langflow.business.sources import bindings, client_for, path_value

    if connection.kind != "api":
        msg = "Select an API connection"
        raise ValueError(msg)
    path, method = config.get("path", ""), config.get("method", "GET")
    if not path.startswith("/") or path.startswith("//") or "://" in path or method not in {"GET", "POST"}:
        msg = "Use GET or POST and a path relative to the registered API connection"
        raise ValueError(msg)
    if not isinstance(parameters, dict) or not isinstance(record, dict):
        msg = "Preview parameters and upstream record must be JSON objects"
        raise TypeError(msg)
    payload = bindings(config.get("body", {}), parameters, record)
    with (
        client_for(connection, settings) as client,
        client.stream(
            method, path, timeout=20, **({"params": payload} if method == "GET" else {"json": payload})
        ) as response,
    ):
        response.raise_for_status()
        if response.status_code == HTTPStatus.ACCEPTED:
            msg = "The API accepted the request but has not returned record data"
            raise ValueError(msg)
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                msg = "Preview exceeds 1 MiB; use narrower test parameters"
                raise ValueError(msg)
        decoded = json.loads(data, parse_float=Decimal)
    for condition in config.get("response_conditions", []):
        if path_value(decoded, condition["path"]) != condition["equals"]:
            msg = "API preview did not satisfy its success contract"
            raise ValueError(msg)
    rows = path_value(decoded, config.get("items_path", ""))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        msg = "The response record path must contain an array of objects"
        raise ValueError(msg)
    rows = rows[:25]
    fields, uncertain = [], []
    names = dict.fromkeys(name for row in rows for name in row)
    for name in names:
        values = [row[name] for row in rows if row.get(name) is not None]
        kinds = {
            "boolean"
            if isinstance(v, bool)
            else "integer"
            if isinstance(v, int)
            else "number"
            if isinstance(v, (float, Decimal))
            else "text"
            if isinstance(v, str)
            else "nested"
            for v in values
        }
        if kinds <= {"integer", "number"} and kinds:
            kind = "number" if "number" in kinds else "integer"
        else:
            kind = next(iter(kinds)) if len(kinds) == 1 and "nested" not in kinds else "text"
        if not kinds or (len(kinds) > 1 and not kinds <= {"integer", "number"}) or "nested" in kinds:
            uncertain.append(name)
        fields.append(
            {
                "name": name,
                "type": kind,
                "required": all(name in row for row in rows),
                "nullable": any(row.get(name) is None for row in rows),
            }
        )
    conflicts = []
    if config.get("field_evidence") and config.get("fields"):
        import pyarrow as pa

        from langflow.business.sources import arrow_schema, normalize

        try:
            validate_evidence(config, connection, settings, owner)
            declared = arrow_schema(config["fields"])
            for row in rows:
                validate_record(row, config["fields"])
                pa.Table.from_pylist([normalize(row, declared)], schema=declared)
        except (ValueError, TypeError, ArithmeticError, pa.ArrowException) as exc:
            conflicts.append(str(exc)[:500])
    return {
        "fields": fields,
        "rows": safe_json(rows),
        "sample_limit": 25,
        "uncertain_types": uncertain,
        "contract_errors": conflicts,
        "field_evidence": sample_evidence(config, fields, connection, settings, owner),
    }
