# ruff: noqa: S608 - all SQL values and identifiers are quoted.
"""Versioned source dictionaries: exact interpretation, never model-generated code meanings."""

import json
from functools import lru_cache
from pathlib import Path

from langflow.business.datasets import ident, literal

DIRECTORY = Path(__file__).with_name("code_dictionaries")
DICTIONARIES = ["wst364.8-2023-cv04.30.002"]
SUFFIXES = ["code_name", "code_status", "code_version", "code_source"]


@lru_cache
def load(dictionary_id):
    if dictionary_id not in DICTIONARIES:
        msg = "Unknown code dictionary"
        raise ValueError(msg)
    return json.loads((DIRECTORY / (dictionary_id + ".json")).read_text())


def fields(config):
    if not config.get("dictionary"):
        return []
    prefix = config.get("result_prefix", "classification")
    return [{"name": prefix + "_" + suffix, "type": "text"} for suffix in SUFFIXES]


def validate(config, source_fields):
    if not config.get("dictionary"):
        return
    load(config["dictionary"]["id"])
    if config["dictionary"]["field"] not in source_fields:
        msg = "Dictionary code field must exist upstream"
        raise ValueError(msg)
    if any(f["name"] in source_fields for f in fields(config)):
        msg = "Dictionary output fields already exist"
        raise ValueError(msg)


def query(config, source):
    dictionary = load(config["dictionary"]["id"])
    rows = []
    for entry in dictionary["records"]:
        name = entry["citations"][0]["name"] if entry["status"] == "resolved" else None
        citation = json.dumps(
            {"url": dictionary["source"], "sha256": dictionary["source_sha256"], "entries": entry["citations"]},
            ensure_ascii=False,
        )
        rows.append("(" + ", ".join(map(literal, [entry["code"], name, entry["status"], citation])) + ")")
    code = "s." + ident(config["dictionary"]["field"])
    columns = [
        "d.name",
        (
            f"CASE WHEN {code} IS NULL OR trim(CAST({code} AS VARCHAR))='' THEN 'missing_code' "
            "ELSE coalesce(d.status, 'unknown_code') END"
        ),
        literal(dictionary["version"]),
        "d.citation",
    ]
    outputs = ", ".join(
        f"{value} AS {ident(field['name'])}" for value, field in zip(columns, fields(config), strict=True)
    )
    return (
        f"SELECT s.*, {outputs} FROM {source} s LEFT JOIN (VALUES {', '.join(rows)}) "
        f"d(code, name, status, citation) ON CAST({code} AS VARCHAR)=d.code"
    )


def resolved(config):
    if not config.get("dictionary"):
        return "TRUE"
    return ident(config.get("result_prefix", "classification") + "_code_status") + "='resolved'"
