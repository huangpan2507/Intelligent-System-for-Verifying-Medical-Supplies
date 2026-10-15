# ruff: noqa: S608 - dataset paths come from DatasetStore; row ids are bound parameters.
"""Read saved result evidence as business records without querying source systems."""

import json
from collections import defaultdict

import duckdb
from sqlalchemy import select

from langflow.business.datasets import ROW_ID, DatasetStore, ident, safe_json
from langflow.business.models import ExternalRequest, Release, ResultEvidence


def object_value(value):
    return json.loads(value) if isinstance(value, str) else value


def snapshot_rows(store, dataset_id, row_ids):
    """Row identity is independent of physical Parquet order and pagination."""
    store.get(dataset_id)
    if not row_ids:
        return {}
    with store.engine() as db:
        cursor = db.execute(
            f"SELECT * FROM {store.relation(dataset_id)} WHERE {ident(ROW_ID)} IN (SELECT unnest(?))",
            [list(row_ids)],
        )
        names = [c[0] for c in cursor.description]
        return {row[ROW_ID]: safe_json(row) for row in (dict(zip(names, r, strict=True)) for r in cursor.fetchall())}


def source_detail(database, task_id, result_id, evidence_id):
    with database.sessions() as session:
        evidence = session.get(ResultEvidence, evidence_id)
        if evidence is None or evidence.result_id != result_id:
            message = "Evidence not found in this result"
            raise ValueError(message)
        if evidence.kind == "recognition":
            request = session.get(ExternalRequest, evidence.request_id)
            if request is None or request.task_id != task_id:
                message = "Recognition request not found in this task"
                raise ValueError(message)
            return {
                "kind": "recognition",
                "request": safe_json({c.name: getattr(request, c.name) for c in request.__table__.columns}),
            }
        if evidence.kind != "source":
            message = "Evidence has no source snapshot"
            raise ValueError(message)
        store = DatasetStore(database, task_id)
        dataset = store.get(evidence.source_dataset_id)
        row = snapshot_rows(store, dataset.id, [evidence.source_row_id]).get(evidence.source_row_id)
        if row is None:
            message = "Source record not found in saved snapshot"
            raise ValueError(message)
        return {
            "kind": "source",
            "dataset_id": dataset.id,
            "row_id": evidence.source_row_id,
            "name": dataset.name,
            "fields": dataset.fields,
            "record": row,
            "original_record": object_value(row["_raw_record"]) if row.get("_raw_record") else None,
            "provenance": dataset.provenance,
        }


class EvidenceView:
    """Resolve parents from saved request rows and lineage, never from request numbers."""

    def __init__(self, database, task_id, result):
        self.store = DatasetStore(database, task_id)
        with database.sessions() as session:
            self.evidence = list(
                session.scalars(
                    select(ResultEvidence).where(ResultEvidence.result_id == result.id).order_by(ResultEvidence.ordinal)
                )
            )
            release = session.get(Release, result.release_id)
            profile = release.package.get("result_templates", {}).get(result.node_id, {})
            self.settlement_nodes = {s["node"] for s in profile.get("obligation", {}).get("sources", [])}
        self.items = {}
        self.records = {}
        self.datasets = {}
        self.refs = {}
        self.parents = defaultdict(set)
        self.used_api = set()
        self._load_sources()
        self._link_images()
        self.image_count = len(
            {e.context.get("address") for e in self.evidence if e.kind == "image" and e.context.get("address")}
        )

    def role(self, dataset):
        if dataset.node_id in self.settlement_nodes:
            return "settlement"
        query = dataset.provenance.get("query", {})
        outputs = {r.get("output", r.get("field")) for r in query.get("returns", [])}
        if "study_ris_study_id" in outputs:
            return "study"
        if "series_id" in outputs:
            return "series"
        if query.get("collection"):
            return "api"
        return "other"

    def _load_sources(self):
        grouped = defaultdict(list)
        for e in self.evidence:
            if e.kind == "source":
                grouped[e.source_dataset_id].append(e)
        for dataset_id, refs in grouped.items():
            try:
                dataset = self.store.get(dataset_id)
                self.datasets[dataset_id] = dataset
                records = snapshot_rows(self.store, dataset_id, [e.source_row_id for e in refs])
            except (ValueError, OSError, duckdb.Error):
                records, dataset = {}, None
            for e in refs:
                record = records.get(e.source_row_id)
                role = self.role(dataset) if dataset else "other"
                self.refs[(dataset_id, e.source_row_id)] = e.id
                self.items[e.id] = {
                    "id": e.id,
                    "kind": role,
                    "parent": None,
                    "sources": [e.id],
                    "available": record is not None,
                    "details": {},
                    "title": [],
                }
                if record is None:
                    continue
                self.records[e.id] = record
                fields = {
                    "settlement": ["PSN_NAME", "HILIST_NAME", "SETL_FEE_LIST_ID", "CNT", "PRIC", "RPT_NO"],
                    "study": [
                        "proj_name",
                        "ckpt_name",
                        "chk_dt",
                        "chk_modality",
                        "ris_study_id",
                        "rpt_no",
                        "EXAM_PART",
                    ],
                    "series": ["series_description", "chk_modality", "pacs_series_id", "global_id", "ris_study_id"],
                }.get(role, [])
                self.items[e.id]["details"] = {k: record[k] for k in fields if record.get(k) is not None}
                titles = {
                    "settlement": ["HILIST_NAME", "SETL_FEE_LIST_ID"],
                    "study": ["proj_name", "chk_dt", "chk_modality", "ris_study_id"],
                    "series": ["series_description", "chk_modality", "global_id"],
                }.get(role, [])
                self.items[e.id]["title"] = [str(record[k]) for k in titles if record.get(k) not in (None, "")]

    def _api_contexts(self):
        """Recover the exact input row and its original occurrences for each API return."""
        contexts = []
        for dataset_id, dataset in self.datasets.items():
            if self.role(dataset) != "api":
                continue
            parents = dataset.provenance.get("parents", [])
            if len(parents) != 1:
                continue
            refs = [e for e in self.evidence if e.source_dataset_id == dataset_id and e.id in self.records]
            row_ids = {self.records[e.id].get("_request_row_id") for e in refs} - {None}
            try:
                parent_rows = snapshot_rows(self.store, parents[0], row_ids)
                with self.store.engine() as db:
                    origins = db.execute(
                        f"SELECT row_id, source_dataset_id, source_row_id FROM {self.store.lineage(parents[0])} "
                        "WHERE row_id IN (SELECT unnest(?))",
                        [list(row_ids)],
                    ).fetchall()
            except (ValueError, OSError, duckdb.Error):
                continue
            by_row = defaultdict(set)
            for row_id, source_id, source_row in origins:
                if (source_id, source_row) in self.refs:
                    by_row[row_id].add(self.refs[(source_id, source_row)])
            config = dataset.provenance["query"]["collection"]
            for e in refs:
                raw = self.records[e.id]
                source = parent_rows.get(raw.get("_request_row_id"))
                if source is None or any(raw.get(f) is None for f in config["address_fields"]):
                    continue
                context = {
                    "address": "".join(str(raw[f]) for f in config["address_fields"]),
                    **{f: source.get(f) for f in config.get("item_context", [])},
                    **{f: raw.get(f) for f in config.get("item_keys", [])},
                }
                origins = by_row[raw["_request_row_id"]]
                studies = {ref for ref in origins if self.items[ref]["kind"] == "study"}
                series = {ref for ref in origins if self.items[ref]["kind"] == "series"}
                for ref in series:
                    self.parents[ref].update(studies)
                contexts.append((e.id, context, series, object_value(raw.get("_raw_record", {}))))
        return contexts

    def _link_images(self):
        contexts = self._api_contexts()
        for e in self.evidence:
            if e.kind == "recognition":
                self.items[e.id] = {
                    "id": e.id,
                    "kind": "recognition",
                    "parent": None,
                    "available": True,
                    "title": [],
                    "details": e.context,
                    "sources": [],
                }
            if e.kind != "image":
                continue
            matches = [c for c in contexts if all(k in e.context and e.context[k] == v for k, v in c[1].items())]
            source_refs = sorted({m[0] for m in matches})
            self.used_api.update(source_refs)
            series = set().union(*(m[2] for m in matches)) if matches else set()
            parent = next(iter(series)) if len(series) == 1 else None
            details = dict(e.context)
            numbers = {
                str(m[3]["image_instance_number"])
                for m in matches
                if isinstance(m[3], dict) and m[3].get("image_instance_number") is not None
            }
            if len(numbers) == 1:
                details["image_instance_number"] = next(iter(numbers))
            self.items[e.id] = {
                "id": e.id,
                "kind": "image",
                "parent": parent,
                "available": bool(source_refs),
                "title": [str(e.context[k]) for k in ["sop_instance_uid"] if e.context.get(k)],
                "details": details,
                "sources": source_refs,
            }
        for ref, parents in self.parents.items():
            if len(parents) == 1:
                self.items[ref]["parent"] = next(iter(parents))

    def page(self, group, parent, offset, limit):
        def unlinked(item):
            return (
                item["kind"] == "other"
                or (item["kind"] == "api" and item["id"] not in self.used_api)
                or (item["kind"] in {"series", "image"} and not item["parent"])
            )

        all_items = list(self.items.values())
        selected = (
            [i for i in all_items if unlinked(i)]
            if group == "unlinked"
            else [i for i in all_items if i["kind"] == group and (not parent or i["parent"] == parent)]
        )
        selected.sort(key=lambda i: (i["title"], i["id"]))
        counts = {k: sum(i["kind"] == k for i in all_items) for k in ["settlement", "study", "series", "recognition"]}
        counts.update(image=self.image_count, unlinked=sum(unlinked(i) for i in all_items))
        items = selected[offset : offset + limit]
        for item in items:
            item["children"] = sum(i["parent"] == item["id"] for i in all_items)
        return {"items": items, "total": len(selected), "counts": counts, "offset": offset, "limit": limit}
