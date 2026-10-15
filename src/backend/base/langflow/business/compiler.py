# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Validate registered DAG capabilities and propagate output schemas before publication."""

import contextlib
import hashlib
import re
from pathlib import Path

import duckdb
import jsonschema

from langflow.business.catalog import CATALOG, PLUGINS
from langflow.business.connections import metadata
from langflow.business.contracts import CONTRACT_VERSION, Graph
from langflow.business.datasets import ROW_ID, ident, register_functions
from langflow.business.field_schema import validate_bindings, validate_evidence, validate_references
from langflow.business.models import Connection, Release
from langflow.business.relational import TYPES, identity_queries, join_queries, unary_query
from langflow.business.task_input import CONTEXT, CONTRACT, parameter_definitions
from langflow.business.validate_migration import ISSUES_VERSION

# Only execution and contract dependencies. Demo data, management routes and UI do not execute a release.
EXECUTION_MODULES = {
    "catalog",
    "compiler",
    "components",
    "connections",
    "contracts",
    "datasets",
    "expressions",
    "models",
    "plugins",
    "relational",
    "runtime",
    "sources",
    "coverage",
    "requests",
    "field_schema",
    "task_input",
    "validate_migration",
    "classification",
    "classification_config",
    "collection",
    "lookup",
    "code_dictionary",
    "result_templates",
    "results",
}


def runtime_digest():
    import importlib.metadata

    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(p for p in root.glob("*.py") if p.stem in EXECUTION_MODULES):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for path in sorted((root / "code_dictionaries").glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for path in sorted((root / "result_templates").glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    import inspect

    for parent in root.parents:
        wrappers = parent / "deploy/verification/components/business"
        if wrappers.is_dir():
            for path in sorted(wrappers.glob("*.py")):
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
            break
    for kind, plugin in sorted(PLUGINS.items()):
        digest.update(kind.encode())
        module = inspect.getmodule(plugin.execute)
        if not module or not getattr(module, "__file__", None):
            msg = f"Plugin source unavailable for release fingerprint: {kind}"
            raise ValueError(msg)
        digest.update(Path(module.__file__).read_bytes())
    for name in ["duckdb", "pyarrow", "sqlalchemy", "lfx", "psycopg", "pymysql"]:
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            digest.update((name + importlib.metadata.version(name)).encode())
    return digest.hexdigest()


def ordered_nodes(graph):
    ids = [n["id"] for n in graph["nodes"]]
    if len(ids) != len(set(ids)):
        msg = "Duplicate node identifiers"
        raise ValueError(msg)
    remaining = set(ids)
    order = []
    for edge in graph["edges"]:
        if edge["source"] not in remaining or edge["target"] not in remaining:
            msg = "Edge references a missing node"
            raise ValueError(msg)
    while remaining:
        ready = [
            i
            for i in ids
            if i in remaining and not any(e["target"] == i and e["source"] in remaining for e in graph["edges"])
        ]
        if not ready:
            msg = "Business graphs must be acyclic; use a published subflow for reuse"
            raise ValueError(msg)
        order.extend(ready)
        remaining.difference_update(ready)
    return order


def sql_type(value):
    upper = str(value).upper()
    if upper in TYPES:
        return TYPES[upper]
    if "DECIMAL" in upper or "NUMERIC" in upper:
        dimensions = re.search(r"\((\d+)\s*,\s*(\d+)\)", upper)
        return f"DECIMAL({dimensions[1]},{dimensions[2]})" if dimensions else "DECIMAL(38,6)"
    if "INT" in upper:
        return "BIGINT"
    if "FLOAT" in upper or "DOUBLE" in upper or "REAL" in upper:
        return "DOUBLE"
    if "BOOL" in upper:
        return "BOOLEAN"
    if "TIMESTAMP" in upper or "DATETIME" in upper:
        return "TIMESTAMPTZ" if "TZ" in upper or "WITH TIME ZONE" in upper else "TIMESTAMP"
    if upper == "DATE" or upper.startswith("DATE32"):
        return "DATE"
    if "BINARY" in upper or "BLOB" in upper or "BYTEA" in upper:
        return "BLOB"
    return TYPES.get(str(value), "VARCHAR")


def inspect_graph(graph, database, settings, owner, *, strict=True):
    graph = Graph.model_validate(graph).model_dump()
    order = ordered_nodes(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    outputs, errors, connections, children = {}, {}, {}, {}
    parameters = {}
    classification_prompts = {}
    result_templates = {}
    single_output = sum(n["kind"] == "output" for n in nodes.values()) == 1
    task_entry = any(n["kind"] == "taskinput" for n in nodes.values())
    if task_entry and sum(n["kind"] in {"taskinput", "parameters"} for n in nodes.values()) != 1:
        errors["task_input"] = "A regulatory workflow needs one Task Start and no generic Parameters node"
    with duckdb.connect() as db:
        register_functions(db)
        for node_id in order:
            node = nodes[node_id]
            try:
                kind, config = node["kind"], node["config"]
                if kind == "output":
                    from langflow.business.result_templates import prepare_output

                    profile = prepare_output(config, single=single_output)
                    if profile:
                        result_templates[node_id] = profile
                if kind not in CATALOG:
                    msg = f"Unregistered component: {kind}"
                    raise ValueError(msg)
                info = CATALOG[kind]
                jsonschema.validate(config, info["schema"])
                if (
                    kind == "databaselookup"
                    and config.get("binding_source") is not None
                    and config["binding_source"] != {k: config.get(k, "") for k in ("connection", "schema", "table")}
                ):
                    msg = "Database source changed; review field bindings before publication"
                    raise ValueError(msg)
                incoming = [e for e in graph["edges"] if e["target"] == node_id]
                by_input = {}
                for edge in incoming:
                    source_node = nodes[edge["source"]]
                    if edge["port"] not in CATALOG[source_node["kind"]]["ports"]:
                        msg = "Unknown output port"
                        raise ValueError(msg)
                    is_parameters = source_node["kind"] in {"parameters", "taskinput"}
                    if edge["input"] not in info["inputs"] and not is_parameters:
                        msg = "Unknown input port"
                        raise ValueError(msg)
                    if not is_parameters or source_node["config"].get("dataset_fields"):
                        by_input.setdefault(edge["input"], []).append(outputs[edge["source"]][edge["port"]])
                for name in info["inputs"]:
                    if not by_input.get(name) and name not in info.get("optional_inputs", []):
                        msg = f"Missing input: {name}"
                        raise ValueError(msg)
                    if len(by_input.get(name, [])) > 1 and not info.get("multiple"):
                        msg = f"Input {name} accepts one dataset"
                        raise ValueError(msg)
                conn = None
                if config.get("connection"):
                    with database.sessions() as session:
                        conn = session.get(Connection, config["connection"])
                    if not conn or conn.owner_id != owner:
                        msg = "Connection is unavailable to this owner"
                        raise ValueError(msg)
                    connections[conn.id] = {
                        "id": conn.id,
                        "kind": conn.kind,
                        "config": conn.config,
                        "revision": conn.revision,
                    }
                if kind in {"parameters", "taskinput"}:
                    if kind == "taskinput" and incoming:
                        msg = "Task Start cannot receive upstream inputs"
                        raise ValueError(msg)
                    for param in parameter_definitions(node):
                        if param["name"] in parameters:
                            msg = "Duplicate task parameter"
                            raise ValueError(msg)
                        parameters[param["name"]] = param
                    outputs[node_id] = {
                        "data": config.get("dataset_fields", [])
                        + ([{"name": ROW_ID, "type": "BIGINT"}] if config.get("dataset_fields") else [])
                    }
                    continue
                available = {port: [f for schema in schemas for f in schema] for port, schemas in by_input.items()}
                task_parameters = {
                    p["name"]
                    for n in nodes.values()
                    if n["kind"] in {"parameters", "taskinput"}
                    for p in parameter_definitions(n)
                }
                if task_entry:
                    task_parameters.update(p["name"] for p in CONTEXT)
                validate_bindings(config.get("body", {}), available.get("data", []), task_parameters)
                for condition in [] if kind == "database" and config.get("sql") else config.get("conditions", []):
                    if sum(key in condition for key in ("value", "parameter", "right_field")) > 1:
                        msg = "Choose one condition value source: constant, task parameter or field"
                        raise ValueError(msg)
                    if condition.get("parameter") and condition["parameter"] not in task_parameters:
                        msg = f"Unknown condition parameter: {condition['parameter']}"
                        raise ValueError(msg)
                if kind == "database":
                    if config.get("timezone"):
                        from zoneinfo import ZoneInfo

                        ZoneInfo(config["timezone"])
                    if config.get("sql"):
                        fields = config.get("fields", [])
                        if not fields:
                            msg = "Advanced SQL requires declared output fields and types; use query preview"
                            raise ValueError(msg)
                        validate_evidence(config, conn, settings, owner)
                    elif config.get("table"):
                        fields = metadata(conn, settings, config["table"], config.get("schema"))["fields"]
                    else:
                        msg = "Choose a table or provide a SELECT query"
                        raise ValueError(msg)
                    available["data"] = fields
                    validate_references(
                        {**config, "conditions": []} if config.get("sql") else config,
                        info["schema"],
                        available,
                        outputs,
                    )
                    queries = None
                elif kind == "classification":
                    from langflow.business import code_dictionary
                    from langflow.business.classification import output_fields, validate_config
                    from langflow.business.classification_config import system_message

                    if conn.kind not in {"model", "api"}:
                        msg = "Choose a model service connection"
                        raise ValueError(msg)
                    validate_config(config, [f["name"] for f in available["data"]])
                    available["data"] = [*available["data"], *code_dictionary.fields(config)]
                    fields = [*available["data"], *output_fields(config)]
                    classification_prompts[node_id] = system_message(config)
                    queries = None
                elif kind == "databaselookup":
                    from langflow.business.lookup import lookup_query, result_queries

                    remote_fields = metadata(conn, settings, config["table"], config.get("schema"))["fields"]
                    available["database"] = remote_fields
                    remote_fields = [*remote_fields, {"name": ROW_ID, "type": "BIGINT"}]
                    source_relation = empty_relation(db, node_id + "_input", available["data"])
                    remote_relation = empty_relation(db, node_id + "_remote", remote_fields)
                    query = lookup_query(
                        config, source_relation, [f["name"] for f in available["data"]], remote_relation
                    )
                    available["result"] = describe_query(db, query)
                    placeholders = dict.fromkeys(task_parameters)
                    queries = result_queries(
                        config, f"({query})", [f["name"] for f in available["result"]], placeholders
                    )
                    outputs[node_id] = {port: describe_query(db, q) for port, q in queries.items()}
                elif kind in {"api", "file"}:
                    fields = config.get("fields", [])
                    if not fields:
                        msg = "Declare source fields using metadata or file preview"
                        raise ValueError(msg)
                    if kind == "api":
                        if conn.kind != "api":
                            msg = "Choose an API connection"
                            raise ValueError(msg)
                        validate_evidence(config, conn, settings, owner)
                        if config.get("completeness", {}).get("scope") == "object" and not by_input.get("data"):
                            msg_0 = "Object completeness requires an input dataset defining independent requests"
                            raise ValueError(msg_0)
                        fields = [
                            *fields,
                            {"name": "_raw_record", "type": "text"},
                            {"name": "_raw_facts", "type": "text"},
                            {"name": "_request_row_id", "type": "BIGINT"},
                        ]
                        input_fields = {f["name"]: f for f in by_input.get("data", [[]])[0]}
                        for name in config.get("context_fields", []):
                            fields.append({**input_fields[name], "name": "_context_" + name})
                    queries = None
                    if kind == "api" and config.get("collection"):
                        from langflow.business.collection import collection_query

                        if not available.get("data"):
                            msg = "API collection requires an upstream dataset"
                            raise ValueError(msg)
                        available["response"] = config["fields"]
                        raw = empty_relation(db, node_id + "_response", [*fields, {"name": ROW_ID, "type": "BIGINT"}])
                        src = empty_relation(db, node_id + "_input", available["data"])
                        issues = empty_relation(
                            db, node_id + "_issues", [{"name": "_request_row_id", "type": "BIGINT"}]
                        )
                        fields = describe_query(db, collection_query(config, src, raw, issues))
                elif kind == "model" or kind in PLUGINS:
                    fields = list(by_input["data"][0])
                    additions = config.get("fields", []) if kind == "model" else PLUGINS[kind].output_fields
                    reserved = {ROW_ID, "_issue_reason", "_model_response", "_request_id"}
                    collisions = {f["name"] for f in fields} & {f["name"] for f in additions}
                    if collisions:
                        msg = f"Model output fields already exist: {sorted(collisions)}"
                        raise ValueError(msg)
                    fields = (
                        [f for f in fields if f["name"] not in reserved]
                        + additions
                        + [
                            {"name": "_issue_reason", "type": "text"},
                            {"name": "_model_response", "type": "text"},
                            {"name": "_request_id", "type": "text"},
                        ]
                    )
                    available["result"] = fields
                    queries = None
                elif kind == "subflow":
                    with database.sessions() as session:
                        child = session.get(Release, config["release_id"])
                        from langflow.business.models import Scheme

                        scheme = session.get(Scheme, child.scheme_code) if child else None
                    if not scheme or scheme.owner_id != owner:
                        msg = "Subflow release is not available"
                        raise ValueError(msg)
                    if child.package.get("task_input"):
                        msg = "Regulatory Task Start must run as a top-level task, not a subflow"
                        raise ValueError(msg)
                    if child.package["runtime_digest"] != runtime_digest():
                        msg = "Subflow runtime changed; republish the child first"
                        raise ValueError(msg)
                    child_inputs = [
                        n
                        for n in child.package["graph"]["nodes"]
                        if n["kind"] == "parameters" and n["config"].get("dataset_fields")
                    ]
                    for child_input in child_inputs:
                        available = {f["name"]: f for f in by_input.get("data", [[]])[0]}
                        for field in child_input["config"]["dataset_fields"]:
                            if field["name"] not in available or sql_type(available[field["name"]]["type"]) != sql_type(
                                field["type"]
                            ):
                                msg = f"Subflow input field missing or incompatible: {field['name']}"
                                raise ValueError(msg)
                    output_nodes = {n["id"] for n in child.package["graph"]["nodes"] if n["kind"] == "output"}
                    if config["output_node"] not in output_nodes:
                        msg = "Choose a published result output of the subflow"
                        raise ValueError(msg)
                    children[child.id] = child.package
                    fields = child.package["schemas"][config["output_node"]]["data"]
                    queries = None
                else:
                    relations = {}
                    for port, schemas in by_input.items():
                        relations[port] = []
                        for index, schema in enumerate(schemas):
                            name = f"{node_id}_{port}_{index}"
                            columns = ", ".join(f"{ident(f['name'])} {field_sql_type(f)}" for f in schema)
                            db.execute(f"CREATE TABLE {ident(name)} ({columns})")
                            relations[port].append(ident(name))
                    if kind == "join":
                        queries = join_queries(
                            config,
                            relations["left"][0],
                            relations["right"][0],
                            [f["name"] for f in by_input["left"][0]],
                            [f["name"] for f in by_input["right"][0]],
                        )
                    elif kind == "union":
                        if config.get("deduplicate"):
                            msg_0 = (
                                "Union deduplicate=true is retired: append here "
                                "and declare identity in a downstream Validate node"
                            )
                            raise ValueError(msg_0)
                        queries = {"data": " UNION ALL BY NAME ".join(f"SELECT * FROM {r}" for r in relations["data"])}
                    elif kind == "validate" and config.get("identity"):
                        queries = identity_queries(
                            config,
                            relations["data"][0],
                            [f["name"] for f in by_input["data"][0]],
                            "SELECT NULL::BIGINT row_id, NULL::VARCHAR facts WHERE FALSE",
                        )
                    else:
                        placeholders = {key: value.get("default") for key, value in parameters.items()}
                        if task_entry:
                            placeholders.update({key: None for key in task_parameters if key not in placeholders})
                        queries = unary_query(
                            kind, config, relations["data"][0], [f["name"] for f in by_input["data"][0]], placeholders
                        )
                    outputs[node_id] = {}
                    for port, query in queries.items():
                        outputs[node_id][port] = [
                            {"name": row[0], "type": row[1], "nullable": row[2] != "NO"}
                            for row in db.execute(f"DESCRIBE ({query})").fetchall()
                        ]
                    if kind == "compare" and config.get("calculations"):
                        available["data"] = outputs[node_id]["data"]
                    if kind == "aggregate":
                        outputs[node_id]["members"] = [
                            {"name": "group_row_id", "type": "BIGINT"},
                            {"name": "source_row_id", "type": "BIGINT"},
                        ]
                if kind != "database":
                    validate_references(config, info["schema"], available, outputs)
                if queries is None:
                    fields = [f for f in fields if f["name"] != ROW_ID] + [
                        {"name": ROW_ID, "type": "BIGINT", "nullable": False}
                    ]
                    outputs[node_id] = dict.fromkeys(info["ports"], fields)
                    if kind == "model" or kind in PLUGINS:
                        outputs[node_id]["issues"] = [{**f, "nullable": True} for f in fields]
                    if kind == "api" and not config.get("collection"):
                        outputs[node_id]["issues"] = [
                            {"name": n, "type": t}
                            for n, t in [
                                ("_request_row_id", "BIGINT"),
                                ("page", "BIGINT"),
                                ("_issue_reason", "text"),
                                ("_raw_response", "text"),
                                (ROW_ID, "BIGINT"),
                            ]
                        ]
            except (ValueError, KeyError, jsonschema.ValidationError, duckdb.Error) as exc:
                errors[node_id] = str(exc).split("\n")[0]
                outputs[node_id] = {}
    if not any(n["kind"] == "output" for n in nodes.values()):
        errors["graph"] = "A published workflow needs at least one result output"
    if sum(n["kind"] == "output" and bool(n["config"].get("primary")) for n in nodes.values()) > 1:
        errors["graph"] = "Choose at most one primary result output"
    from langflow.business.coverage import declaration

    obligation = {"mode": "ordinary"}
    try:
        obligation = declaration(graph, outputs)
    except ValueError as exc:
        errors["obligation"] = str(exc)
    if strict and errors:
        raise ValueError(errors)
    return {
        "graph": graph,
        "schemas": outputs,
        "classification_prompts": classification_prompts,
        "result_templates": result_templates,
        "errors": errors,
        "parameters": list(parameters.values()),
        "task_input": CONTRACT if task_entry else None,
        "connections": connections,
        "subflows": children,
        "runtime_digest": runtime_digest(),
        "contract_version": CONTRACT_VERSION,
        "validate_issues_version": ISSUES_VERSION,
        "obligation": obligation,
        "summary": {
            "sources": [
                {"node": n["id"], "kind": n["kind"], "configuration": n["config"]}
                for n in nodes.values()
                if n["kind"] in {"database", "api", "file"}
            ],
            "conditions": [
                {"node": n["id"], "configuration": n["config"]} for n in nodes.values() if n["kind"] == "filter"
            ],
            "obligation": obligation,
        },
    }


def field_sql_type(field):
    if field["type"] == "number":
        return f"DECIMAL({field.get('precision', 38)},{field.get('scale', 6)})"
    return sql_type(field["type"])


def empty_relation(db, name, fields):
    columns = ", ".join(f"{ident(f['name'])} {field_sql_type(f)}" for f in fields)
    db.execute(f"CREATE TABLE {ident(name)} ({columns})")
    return ident(name)


def describe_query(db, query):
    return [
        {"name": r[0], "type": r[1], "nullable": r[2] != "NO"} for r in db.execute(f"DESCRIBE ({query})").fetchall()
    ]
