"""Registered node capabilities and the same form schemas used by validation and UI."""

from langflow.business.code_dictionary import DICTIONARIES


def string(**extra):
    return {"type": "string", **extra}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def array(item, **extra):
    return {"type": "array", "items": item, **extra}


FIELD = string(format="field", minLength=1)
FIELDS = array(FIELD)
CONNECTION = string(format="connection", minLength=1)
CONDITION = obj(
    {
        "field": FIELD,
        "op": string(enum=["eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "contains", "is_null", "not_null"]),
        "value": {},
        "parameter": string(format="parameter", minLength=1),
        "right_field": FIELD,
    },
    ["field", "op"],
)
CONDITION["format"] = "condition"
CONDITIONS = array(CONDITION)
DATABASE_CONDITION = {
    **CONDITION,
    "properties": {
        key: (string(enum=["eq", "ne", "gt", "ge", "lt", "le", "in"]) if key == "op" else value)
        for key, value in CONDITION["properties"].items()
        if key != "right_field"
    },
}
SCHEMA_FIELDS = array(
    obj(
        {
            "name": string(),
            "type": string(enum=["text", "integer", "number", "boolean", "date", "datetime"]),
            "nullable": {"type": "boolean"},
            "required": {"type": "boolean"},
            "precision": {"type": "integer", "minimum": 1, "maximum": 38},
            "scale": {"type": "integer", "minimum": 0, "maximum": 38},
            "timezone": string(),
            "unit": string(),
        },
        ["name", "type"],
    )
)
PARAMETERS = array(
    obj(
        {
            "name": string(),
            "type": string(enum=["string", "integer", "number", "boolean"]),
            "required": {"type": "boolean"},
            "default": {},
            "enum": array({}),
            "description": string(),
        },
        ["name", "type"],
    )
)
DATASET_REFERENCE = obj({"node": string(format="node"), "port": string(format="output_port")}, ["node", "port"])
RESULT_REFERENCE = obj(
    {
        **DATASET_REFERENCE["properties"],
        "fallback": {"type": "boolean"},
        "status_field": FIELD,
        "reason_field": FIELD,
        "evidence_field": FIELD,
        "status": string(enum=["equal", "different", "uncompared", "not_applicable"]),
        "reason": string(),
    },
    ["node", "port"],
)
OBLIGATION = obj(
    {
        "mode": string(enum=["ordinary", "verification"]),
        "sources": array(
            obj({"node": string(format="node"), "identity": string(format="node")}, ["node", "identity"]), minItems=1
        ),
        "checks": array(
            obj(
                {
                    "name": string(minLength=1),
                    "units": DATASET_REFERENCE,
                    "results": array(RESULT_REFERENCE, minItems=1),
                },
                ["name", "units", "results"],
            ),
            minItems=1,
        ),
        "dispositions": array(
            obj(
                {
                    **DATASET_REFERENCE["properties"],
                    "status": string(enum=["excluded", "uncompared", "issue"]),
                    "reason": string(minLength=1),
                    "status_field": FIELD,
                    "reason_field": FIELD,
                },
                ["node", "port"],
            )
        ),
    },
    ["mode"],
)

CHECKS = obj(
    {
        "required": array(string(format="field:result")),
        "conditions": array(
            {
                **CONDITION,
                "properties": {
                    **CONDITION["properties"],
                    "field": string(format="field:result"),
                    "right_field": string(format="field:result"),
                },
            }
        ),
    }
)
REMOTE_FIELD = string(format="field:database", minLength=1)

CATALOG = {
    "classification": {
        "ports": ["data", "issues"],
        "inputs": ["data"],
        "schema": obj(
            {
                "result_prefix": string(pattern="^[A-Za-z][A-Za-z0-9_]{0,63}$", default="classification"),
                "dictionary": obj({"id": string(enum=DICTIONARIES), "field": FIELD}, ["id", "field"]),
                "classification_fields": array(
                    obj({"field": FIELD, "role": string(enum=["evidence", "context"])}, ["field", "role"]), minItems=1
                ),
                "category_routes": array(
                    obj({"category": string(minLength=1), "continue": {"type": "boolean"}}, ["category", "continue"]),
                    minItems=1,
                ),
                "business_guidance": string(format="multiline"),
                "ambiguity_hints": array(string(minLength=1)),
                "rules": array(
                    obj(
                        {
                            "fields": FIELDS,
                            "op": string(enum=["contains", "eq", "contains_all"]),
                            "keywords": array(string(minLength=1), minItems=1),
                            "value": string(minLength=1),
                            "category": string(minLength=1),
                            "when": array(obj({"field": FIELD, "value": string()}, ["field", "value"])),
                        },
                        ["op", "category"],
                    )
                ),
                "conflicts": array(
                    obj(
                        {
                            "category": string(),
                            "field": FIELD,
                            "contains": string(minLength=1),
                            "when": array(obj({"field": FIELD, "value": string()}, ["field", "value"])),
                        },
                        ["category", "field", "contains"],
                    )
                ),
                "connection": CONNECTION,
                "path": string(),
                "model": string(),
                "max_calls": {"type": "integer", "minimum": 1, "maximum": 100000},
            },
            [
                "classification_fields",
                "category_routes",
                "business_guidance",
                "rules",
                "connection",
                "path",
                "model",
            ],
        ),
    },
    "databaselookup": {
        "ports": ["data", "issues"],
        "inputs": ["data"],
        "schema": obj(
            {
                "connection": CONNECTION,
                "schema": string(format="database_schema"),
                "table": string(format="table"),
                "timezone": string(),
                "binding_source": obj(
                    {"connection": string(), "schema": string(), "table": string()},
                    ["connection", "schema", "table"],
                ),
                "keys": array(obj({"left": FIELD, "right": REMOTE_FIELD}, ["left", "right"]), minItems=1),
                "conditions": array(
                    {**DATABASE_CONDITION, "properties": {**DATABASE_CONDITION["properties"], "field": REMOTE_FIELD}}
                ),
                "source_identity": obj(
                    {"name": string(), "namespace": string(), "keys": array(REMOTE_FIELD, minItems=1)},
                    ["name", "namespace", "keys"],
                ),
                "source_required": array(REMOTE_FIELD),
                "returns": array(
                    obj(
                        {
                            "field": REMOTE_FIELD,
                            "output": string(minLength=1),
                            "type": string(enum=["text", "integer", "number", "datetime"]),
                            "timezone": string(),
                        },
                        ["field", "output"],
                    ),
                    minItems=1,
                ),
                "checks": CHECKS,
            },
            ["connection", "table", "keys", "returns"],
        ),
    },
    "taskinput": {
        "ports": ["data"],
        "inputs": [],
        "schema": obj({}),
    },
    "parameters": {
        "ports": ["data"],
        "inputs": [],
        "schema": obj({"parameters": PARAMETERS, "dataset_fields": SCHEMA_FIELDS}),
    },
    "database": {
        "ports": ["data"],
        "inputs": [],
        "schema": obj(
            {
                "connection": CONNECTION,
                "table": string(format="table"),
                "schema": string(format="database_schema"),
                "timezone": string(),
                "conditions": array(DATABASE_CONDITION),
                "sql": string(format="multiline"),
                "parameters": array(string()),
                "fields": SCHEMA_FIELDS,
                "field_evidence": {"type": "object"},
            },
            ["connection"],
        ),
    },
    "api": {
        "ports": ["data", "issues"],
        "inputs": ["data"],
        "optional_inputs": ["data"],
        "schema": obj(
            {
                "connection": CONNECTION,
                "path": string(),
                "method": string(enum=["GET", "POST"]),
                "body": {"type": "object"},
                "items_path": string(),
                "pagination": string(enum=["none", "cursor", "page"]),
                "cursor_path": string(),
                "cursor_parameter": string(),
                "page_parameter": string(),
                "max_calls": {"type": "integer", "minimum": 1, "maximum": 1000000},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 10000},
                "fields": SCHEMA_FIELDS,
                "field_evidence": {"type": "object"},
                "completeness": obj(
                    {
                        "basis": string(minLength=1),
                        "scope": string(enum=["range", "object"]),
                        "complete_path": string(),
                    },
                    ["basis", "scope"],
                ),
                "context_fields": FIELDS,
                "response_conditions": array(obj({"path": string(), "equals": {}}, ["path", "equals"])),
                "collection": obj(
                    {
                        "group_by": array(FIELD, minItems=1),
                        "retain_fields": FIELDS,
                        "item_context": FIELDS,
                        "address_fields": array(string(format="field:response"), minItems=1),
                        "item_keys": array(string(format="field:response"), minItems=1),
                        "output": string(minLength=1),
                    },
                    ["group_by", "retain_fields", "address_fields", "item_keys", "output"],
                ),
            },
            ["connection", "path", "fields"],
        ),
    },
    "file": {
        "ports": ["data"],
        "inputs": [],
        "schema": obj(
            {
                "file_id": string(format="file"),
                "format": string(enum=["csv", "json", "parquet"]),
                "encoding": string(),
                "fields": SCHEMA_FIELDS,
            },
            ["file_id", "format"],
        ),
    },
    "transform": {
        "ports": ["data"],
        "inputs": ["data"],
        "schema": obj(
            {
                "select": FIELDS,
                "transforms": array(
                    obj(
                        {
                            "field": FIELD,
                            "output": string(),
                            "operation": string(enum=["copy", "cast", "map", "expression"]),
                            "type": string(enum=["text", "integer", "number", "boolean", "date", "datetime"]),
                            "precision": {"type": "integer", "minimum": 1, "maximum": 38},
                            "scale": {"type": "integer", "minimum": 0, "maximum": 38},
                            "mapping": {"type": "object"},
                            "expression": string(),
                        },
                        ["output", "operation"],
                    )
                ),
            }
        ),
    },
    "validate": {
        "ports": ["valid", "issues"],
        "inputs": ["data"],
        "schema": obj(
            {
                "required": FIELDS,
                "unique": FIELDS,
                "conditions": CONDITIONS,
                "identity": obj(
                    {"name": string(minLength=1), "namespace": string(minLength=1), "keys": array(FIELD, minItems=1)},
                    ["name", "namespace", "keys"],
                ),
            }
        ),
    },
    "filter": {
        "ports": ["matched", "unmatched", "unknown"],
        "inputs": ["data"],
        "schema": obj({"conditions": CONDITIONS, "logic": string(enum=["and", "or"])}, ["conditions"]),
    },
    "join": {
        "ports": ["data", "issues"],
        "inputs": ["left", "right"],
        "schema": obj(
            {
                "keys": array(
                    obj(
                        {"left": string(format="field:left"), "right": string(format="field:right")}, ["left", "right"]
                    ),
                    minItems=1,
                ),
                "how": string(enum=["full", "left", "inner", "right"]),
                "cardinality": string(enum=["one_to_one", "one_to_many", "many_to_one", "many_to_many"]),
            },
            ["keys"],
        ),
    },
    "aggregate": {
        "ports": ["data", "members"],
        "inputs": ["data"],
        "schema": obj(
            {
                "group_by": FIELDS,
                "metrics": array(
                    obj(
                        {
                            "field": FIELD,
                            "operation": string(enum=["sum", "count", "min", "max", "avg", "collect"]),
                            "output": string(),
                        },
                        ["operation", "output"],
                    ),
                    minItems=1,
                ),
            },
            ["metrics"],
        ),
    },
    "compare": {
        "ports": ["data"],
        "inputs": ["data"],
        "schema": obj(
            {
                "comparisons": array(
                    obj(
                        {
                            "left": FIELD,
                            "right": FIELD,
                            "mode": string(enum=["exact", "numeric", "case_insensitive"]),
                            "tolerance": {"type": "number", "minimum": 0},
                            "null_equal": {"type": "boolean"},
                            "output": string(minLength=1),
                        },
                        ["left", "right"],
                    ),
                    minItems=1,
                )
            },
            ["comparisons"],
        ),
    },
    "model": {
        "ports": ["data", "issues"],
        "inputs": ["data"],
        "schema": obj(
            {
                "connection": CONNECTION,
                "path": string(),
                "input_fields": FIELDS,
                "prompt": string(format="multiline"),
                "fields": SCHEMA_FIELDS,
                "mode": string(enum=["structured", "openai"]),
                "model": string(),
                "max_calls": {"type": "integer", "minimum": 1, "maximum": 100000},
            },
            ["connection", "input_fields", "fields"],
        ),
    },
    "union": {
        "ports": ["data"],
        "inputs": ["data"],
        "multiple": True,
        "schema": obj({"deduplicate": {"type": "boolean"}, "keys": FIELDS}),
    },
    "output": {
        "ports": ["data"],
        "inputs": ["data"],
        "schema": obj(
            {
                "name": string(),
                "columns": FIELDS,
                "key_fields": FIELDS,
                "reason_fields": FIELDS,
                "evidence_fields": FIELDS,
                "primary": {"type": "boolean"},
                "obligation": OBLIGATION,
            },
            ["name"],
        ),
    },
    "subflow": {
        "ports": ["data"],
        "inputs": ["data"],
        "optional_inputs": ["data"],
        "schema": obj(
            {"release_id": string(), "parameters": {"type": "object"}, "output_node": string()},
            ["release_id", "output_node"],
        ),
    },
}

CATALOG["compare"]["schema"]["properties"]["calculations"] = CATALOG["transform"]["schema"]["properties"]["transforms"]

# Optional domain packages share the same registration and publication checks.
from langflow.business.plugins import plugins  # noqa: E402 - Plugin schemas use the form helpers defined above.

PLUGINS = plugins()
CATALOG.update({kind: plugin.specification for kind, plugin in PLUGINS.items()})
