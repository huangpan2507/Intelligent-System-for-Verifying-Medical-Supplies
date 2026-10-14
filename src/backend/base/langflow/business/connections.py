# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Owner-scoped connection metadata; credentials never enter graph or release packages."""

import base64
import hashlib
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pyarrow as pa
from cryptography.fernet import Fernet
from sqlalchemy import DateTime, MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import URL

from langflow.business.datasets import safe_json


def cipher(settings):
    return Fernet(
        base64.urlsafe_b64encode(hashlib.sha256(settings.internal_token.get_secret_value().encode()).digest())
    )


def encrypt(secret, settings):
    return cipher(settings).encrypt(secret.encode()).decode() if secret else ""


def decrypt(secret, settings):
    return cipher(settings).decrypt(secret.encode()).decode() if secret else ""


def engine_for(connection, settings):
    c = connection.config
    if connection.kind not in {"mysql", "postgresql"}:
        msg = "A database connection is required"
        raise ValueError(msg)
    url = URL.create(
        "postgresql+psycopg" if connection.kind == "postgresql" else "mysql+pymysql",
        username=c.get("username"),
        password=decrypt(connection.secret, settings),
        host=c.get("host"),
        port=int(c.get("port") or (5432 if connection.kind == "postgresql" else 3306)),
        database=c.get("database"),
    )
    return create_engine(url, pool_pre_ping=True)


@contextmanager
def readonly(connection, settings):
    engine = engine_for(connection, settings)
    try:
        with engine.connect() as opened:
            db = opened
            if connection.kind == "postgresql":
                db = db.execution_options(isolation_level="REPEATABLE READ")
                db.execute(text("SET TRANSACTION READ ONLY"))
            else:
                db.execute(text("SET TRANSACTION READ ONLY"))
            yield db
            db.rollback()
    finally:
        engine.dispose()


def metadata(connection, settings, table=None, schema=None):
    schema = schema or None
    with readonly(connection, settings) as db:
        inspector = inspect(db)
        if not table:
            return {
                "default_schema": inspector.default_schema_name,
                "schemas": sorted(inspector.get_schema_names()),
                "tables": sorted(
                    set(inspector.get_table_names(schema=schema) + inspector.get_view_names(schema=schema))
                ),
            }
        columns = inspector.get_columns(table, schema=schema)
        return {
            "fields": [
                {
                    "name": c["name"],
                    "type": reflected_type(c["type"]),
                    "nullable": c.get("nullable", True),
                    "comment": c.get("comment") or "",
                }
                for c in columns
            ]
        }


def preview(connection, settings, config, parameters):
    """A bounded sample for binding fields, never proof of the entire source schema."""
    with readonly(connection, settings) as db:
        query, bindings = statement(db, config, parameters)
        query = text(f"SELECT * FROM ({query}) business_preview LIMIT 25") if config.get("sql") else query.limit(25)
        result = db.execute(query, bindings)
        names = list(result.keys())
        rows = [dict(row) for row in result.mappings().fetchmany(25)]
        if len(names) != len(set(names)):
            msg = "Use unique output field names"
            raise ValueError(msg)
        if not config.get("sql"):
            fields = [
                {"name": c.name, "type": reflected_type(c.type), "nullable": c.nullable, "comment": c.comment or ""}
                for c in query.selected_columns
            ]
        else:
            inferred = pa.Table.from_pylist(rows).schema if rows else pa.schema([])
            fields = [
                {
                    "name": name,
                    "type": str(inferred.field(name).type) if name in inferred.names else "text",
                    "nullable": True,
                }
                for name in names
            ]
        uncertain = [f["name"] for f in fields if not any(row.get(f["name"]) is not None for row in rows)]
        return {
            "fields": fields,
            "rows": safe_json(rows),
            "sample_limit": 25,
            "uncertain_types": uncertain if config.get("sql") else [],
        }


def reflected_type(sql_type):
    # SQLAlchemy's generic TIMESTAMP string omits the timezone flag.
    if isinstance(sql_type, DateTime) and sql_type.timezone:
        return "TIMESTAMP WITH TIME ZONE"
    return str(sql_type)


def arrow_type(sql_type):
    try:
        value = sql_type.python_type
    except (NotImplementedError, AttributeError):
        value = str
    if value is bool:
        return pa.bool_()
    if value is int:
        return pa.int64()
    if value is float:
        return pa.float64()
    if value is Decimal:
        return pa.decimal128(min(getattr(sql_type, "precision", None) or 38, 38), getattr(sql_type, "scale", None) or 0)
    if value is datetime:
        return pa.timestamp("us", tz="UTC" if getattr(sql_type, "timezone", False) else None)
    if value is date:
        return pa.date32()
    if value is bytes:
        return pa.binary()
    return pa.string()


def temporal_value(value, sql_type, zone):
    """Bind task text as the reflected date type, never as VARCHAR or host-local time."""
    try:
        value_type = sql_type.python_type
    except (NotImplementedError, AttributeError):
        return value
    if isinstance(value, list):
        return [temporal_value(item, sql_type, zone) for item in value]
    if isinstance(value, str) and value_type in {date, datetime}:
        value = value_type.fromisoformat(value)
    if isinstance(value, datetime) and getattr(sql_type, "timezone", False) and value.tzinfo is None:
        if not zone:
            msg = "Timezone-aware database fields require an offset in the value or an explicit source timezone"
            raise ValueError(msg)
        value = value.replace(tzinfo=ZoneInfo(zone))
    return value


def statement(db, config, parameters):
    if config.get("sql"):
        sql = config["sql"].strip().rstrip(";")
        if ";" in sql or sql.split()[0].lower() not in {"select", "with"}:
            msg = "Advanced queries must contain one read-only SELECT"
            raise ValueError(msg)
        return text(sql), {key: parameters[key] for key in config.get("parameters", [])}
    table = Table(config["table"], MetaData(), schema=config.get("schema") or None, autoload_with=db)
    query = select(table)
    for item in config.get("conditions", []):
        field = table.c[item["field"]]
        value = parameters[item["parameter"]] if item.get("parameter") else item.get("value")
        value = temporal_value(value, field.type, config.get("timezone"))
        op = item.get("op", "eq")
        methods = {
            "eq": field.__eq__,
            "ne": field.__ne__,
            "gt": field.__gt__,
            "ge": field.__ge__,
            "lt": field.__lt__,
            "le": field.__le__,
            "in": field.in_,
        }
        if op not in methods:
            msg = f"Unsupported source condition {op}"
            raise ValueError(msg)
        query = query.where(methods[op](value))
    return query, {}


def read_database(store, node, connection, settings, config, parameters, *, key_fields=None, key_batches=None):
    with readonly(connection, settings) as db:
        query, bindings = statement(db, config, parameters)
        # Reflect before opening a streaming cursor: MySQL cannot run another query
        # on this connection until that cursor has been consumed.
        if config.get("sql"):
            from langflow.business.sources import arrow_schema

            schema = arrow_schema(config["fields"])
        else:
            schema = pa.schema(
                [pa.field(c.name, arrow_type(c.type), nullable=c.nullable) for c in query.selected_columns]
            )

        def batches():
            from sqlalchemy import tuple_

            for keys in key_batches if key_batches is not None else [None]:
                selected = query
                if keys is not None:
                    selected = query.where(tuple_(*(query.selected_columns[k] for k in key_fields)).in_(keys))
                with db.execution_options(yield_per=5000).execute(selected, bindings) as result:
                    names = list(result.keys())
                    if names != schema.names or len(names) != len(set(names)):
                        msg = "Query fields changed; refresh metadata and rebind the source fields"
                        raise ValueError(msg)
                    while batch := [dict(row) for row in result.mappings().fetchmany(5000)]:
                        for row in batch:
                            for field in schema:
                                if (
                                    pa.types.is_string(field.type)
                                    and row[field.name] is not None
                                    and not isinstance(row[field.name], str)
                                ):
                                    import json

                                    row[field.name] = json.dumps(safe_json(row[field.name]), ensure_ascii=False)
                        yield batch

        return store.write_batches(
            node,
            batches(),
            schema,
            provenance={
                "connection_id": connection.id,
                "connection_revision": connection.revision,
                "query": config,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "consistency": "per_source_transaction",
            },
        )
