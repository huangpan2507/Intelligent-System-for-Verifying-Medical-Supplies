# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Bounded-memory immutable Parquet datasets and disk-backed relational execution."""

import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from langflow.business.models import Dataset
from langflow.verification.database import new_id

ROW_ID = "_business_row_id"


class IncompleteReadError(ValueError):
    """A failed read with a sealed, queryable receipt of successfully written rows."""

    def __init__(self, receipt, cause):
        super().__init__(f"Source incomplete ({type(cause).__name__}); saved {receipt['row_count']} rows")
        self.receipt = receipt


def ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, Decimal)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def json_value(value):
    if isinstance(value, (Decimal, datetime, date)):
        return str(value) if isinstance(value, Decimal) else value.isoformat()
    if isinstance(value, bytes):
        import base64

        return {"encoding": "base64", "value": base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)


def safe_json(value):
    return json.loads(json.dumps(value, default=json_value, allow_nan=False))


def register_functions(db):
    def decimal_fits(value: str, precision: int, scale: int) -> bool:
        from decimal import InvalidOperation, localcontext

        try:
            with localcontext() as context:
                context.prec = 80
                number = Decimal(value)
                return (
                    number.is_finite()
                    and abs(number) < Decimal(10) ** (precision - scale)
                    and number == number.quantize(Decimal(10) ** -scale)
                )
        except (InvalidOperation, ValueError):
            return False

    db.create_function("business_decimal_fits", decimal_fits)


def data_root():
    return Path(os.environ.get("BUSINESS_DATA_DIR", "deploy/verification/.cache/business-data")).resolve()


class DatasetStore:
    def __init__(self, database, task_id, root=None):
        self.database = database
        self.task_id = str(UUID(task_id))
        self.root = (Path(root) if root else data_root()) / self.task_id
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, dataset_id):
        return self.root / f"{UUID(dataset_id)}.parquet"

    @contextmanager
    def engine(self):
        db = duckdb.connect(config={"memory_limit": os.environ.get("BUSINESS_MEMORY_LIMIT", "512MB"), "threads": 2})
        try:
            register_functions(db)
            db.execute(f"SET temp_directory={literal(str(self.root / 'spill'))}")
            db.execute("SET preserve_insertion_order=false")
            yield db
        finally:
            db.close()

    def relation(self, dataset_id):
        return f"read_parquet({literal(str(self.path(dataset_id)))})"

    def get(self, dataset_id):
        with self.database.sessions() as session:
            row = session.get(Dataset, dataset_id)
            if row is None or row.task_id != self.task_id:
                msg = "Dataset not found in this task"
                raise ValueError(msg)
            return row

    def register(self, dataset_id, node, port, *, raw=False, provenance=None, name=None):
        parquet = pq.ParquetFile(self.path(dataset_id))
        fields = [{"name": f.name, "type": str(f.type), "nullable": f.nullable} for f in parquet.schema_arrow]
        row = Dataset(
            id=dataset_id,
            task_id=self.task_id,
            node_id=node,
            port=port,
            name=name or node,
            fields=fields,
            row_count=parquet.metadata.num_rows,
            raw=raw,
            provenance=provenance or {},
        )
        with self.database.sessions.begin() as session:
            session.add(row)
        return {
            "id": dataset_id,
            "fields": fields,
            "row_count": row.row_count,
            "node_id": node,
            "port": port,
            "completeness": row.provenance.get("completeness", {"state": "unknown"}),
        }

    def write_batches(self, node, batches, schema, *, port="data", raw=True, provenance=None):
        if ROW_ID in schema.names:
            msg = f"Source field {ROW_ID} is reserved"
            raise ValueError(msg)
        dataset_id = new_id()
        target = self.path(dataset_id)
        full_schema = schema.append(pa.field(ROW_ID, pa.int64(), nullable=False))
        offset = 0
        try:
            with pq.ParquetWriter(str(target), full_schema) as writer:
                for batch in batches:
                    table = batch if isinstance(batch, pa.Table) else pa.Table.from_pylist(batch, schema=schema)
                    table = table.cast(schema).append_column(
                        ROW_ID, pa.array(range(offset, offset + len(table)), type=pa.int64())
                    )
                    writer.write_table(table.cast(full_schema))
                    offset += len(table)
        except Exception as exc:
            # The writer context seals all successfully written row groups before this handler.
            receipt = self.register(
                dataset_id,
                node,
                port,
                raw=raw,
                provenance={
                    **(provenance or {}),
                    "completeness": {"state": "incomplete", "saved_rows": offset, "error": type(exc).__name__},
                },
            )
            raise IncompleteReadError(receipt, exc) from exc
        return self.register(
            dataset_id,
            node,
            port,
            raw=raw,
            provenance={
                "completeness": {"state": "complete", "basis": "query_exhausted"},
                **(provenance or {}),
            },
        )

    def query(self, node, query, *, port="data", parents=None, details=None, name=None):
        dataset_id = new_id()
        with self.engine() as db:
            description = db.execute(f"DESCRIBE ({query})").fetchall()
            # DuckDB exports HUGEINT as floating point in Parquet; explicitly retain integer precision.
            huge = [row[0] for row in description if row[1] in {"HUGEINT", "UHUGEINT"}]
            if huge:
                columns = [
                    f"CAST({ident(row[0])} AS DECIMAL(38,0)) AS {ident(row[0])}" if row[0] in huge else ident(row[0])
                    for row in description
                ]
                query = f"SELECT {', '.join(columns)} FROM ({query})"
            db.execute(f"COPY ({query}) TO {literal(str(self.path(dataset_id)))} (FORMAT PARQUET)")
        states = [self.get(p).provenance.get("completeness", {"state": "unknown"}) for p in (parents or [])]
        state = (
            "incomplete"
            if any(s["state"] == "incomplete" for s in states)
            else ("unknown" if any(s["state"] != "complete" for s in states) else "complete")
        )
        return self.register(
            dataset_id,
            node,
            port,
            provenance={
                "parents": parents or [],
                "completeness": {"state": state},
                **(details or {}),
            },
            name=name,
        )

    def lineage(self, dataset_id):
        """SQL relation linking output row ids to original occurrences (never business keys)."""
        row = self.get(dataset_id)
        if row.provenance.get("lineage"):
            return self.relation(row.provenance["lineage"])
        if row.raw:
            return (
                f"(SELECT {ident(ROW_ID)} AS row_id, {literal(row.id)} AS source_dataset_id, "
                f"{ident(ROW_ID)} AS source_row_id FROM {self.relation(row.id)})"
            )
        return "(SELECT NULL::BIGINT row_id, NULL::VARCHAR source_dataset_id, NULL::BIGINT source_row_id WHERE FALSE)"

    def link(self, ref, mapping, parents):
        """Persist flattened lineage from a mapping of row_id, parent_id and parent_row_id."""
        chunks = [
            f"SELECT m.row_id, p.source_dataset_id, p.source_row_id FROM ({mapping}) m "
            f"JOIN {self.lineage(parent)} p ON m.parent_id={literal(parent)} AND m.parent_row_id=p.row_id"
            for parent in dict.fromkeys(parents)
        ]
        if not chunks:
            return
        lineage = self.query(ref["node_id"], " UNION ".join(chunks), port="lineage", parents=parents)
        with self.database.sessions.begin() as session:
            row = session.get(Dataset, ref["id"])
            row.provenance = {**row.provenance, "lineage": lineage["id"]}

    def facts(self, dataset_id):
        """Recover all original facts even after field projection; compare facts, not hashes."""
        with self.engine() as db:
            sources = [
                r[0]
                for r in db.execute(f"SELECT DISTINCT source_dataset_id FROM {self.lineage(dataset_id)}").fetchall()
            ]
        chunks = []
        for source in sources:
            fields = [
                f["name"]
                for f in self.get(source).fields
                if f["name"] not in {ROW_ID, "_request_row_id", "_raw_record"}
            ]
            # API raw JSON preserves absent versus explicit null and undeclared fields.
            names = {f["name"] for f in self.get(source).fields}
            value = (
                "_raw_facts"
                if "_raw_facts" in names
                else "_raw_record"
                if "_raw_record" in names
                else ("to_json(struct_pack(" + ", ".join(f"{ident(f)} := s.{ident(f)}" for f in sorted(fields)) + "))")
            )
            chunks.append(
                f"SELECT l.row_id, {value} AS fact FROM {self.lineage(dataset_id)} l "
                f"JOIN {self.relation(source)} s ON l.source_dataset_id={literal(source)} "
                f"AND l.source_row_id=s.{ident(ROW_ID)}"
            )
        if not chunks:
            return "SELECT NULL::BIGINT row_id, NULL::VARCHAR facts WHERE FALSE"
        return (
            "SELECT row_id, to_json(list(DISTINCT fact ORDER BY fact)) AS facts FROM ("
            + " UNION ALL ".join(chunks)
            + ") GROUP BY row_id"
        )

    def page(self, dataset_id, offset=0, limit=100):
        row = self.get(dataset_id)
        with self.engine() as db:
            cursor = db.execute(f"SELECT * FROM {self.relation(dataset_id)} LIMIT ? OFFSET ?", [limit, offset])
            names = [c[0] for c in cursor.description]
            rows = [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]
        return {
            "id": row.id,
            "name": row.name,
            "fields": row.fields,
            "total": row.row_count,
            "offset": offset,
            "limit": limit,
            "rows": safe_json(rows),
            "raw": row.raw,
            "provenance": row.provenance,
        }
