"""Prepare synthetic imaging tables from the read-only Doris schema snapshot.

Generate reviewable DDL/rows by default; --apply also seeds the local databases,
registers a connection, and verifies the joins, field discovery, and image API.
No remote database is contacted and no source business records are copied.
"""
# ruff: noqa: S101, PLR2004 - explicit synthetic fixture and acceptance checks.

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import dotenv_values
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import URL, create_engine
from sqlalchemy.schema import CreateTable

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "deploy/business/fixtures/core-flow"
OUTPUT = FIXTURES / "database-sources"
HOSPITAL = "MOCKHOSP0000000001"
SYSTEM = "MOCK-RIS01"
CONNECTION_NAME = "模拟检查与序列 MySQL (核心流程)"
PG_CONNECTION = "537d8c03-3c9a-4c25-8a8e-d66cfc2b187a"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def link_id(organ, system, study):
    # User-specified identifier contract, not a security/password hash.
    return hashlib.md5(f"{organ}_{system}_{study}".encode(), usedforsecurity=False).hexdigest()


def definitions():
    snapshot = json.loads((FIXTURES / "remote-schema-20261013/schema-report.json").read_text())
    tables, changes = {}, []
    for source, target in [
        ("yb_emr_inspection_info_record_s", "INSPECTION_INFO_RECORD"),
        ("yb_dp_series_info_s", "SERIES_INFO"),
    ]:
        table = Table(
            target,
            MetaData(),
            mysql_engine="InnoDB",
            mysql_row_format="DYNAMIC",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_bin",
            comment=f"Synthetic core-flow fixture; field names derived from {source}",
        )
        for item in snapshot["tables"][source]["columns"]:
            name, original = item["Field"], item["Type"]
            length = re.fullmatch(r"varchar\((\d+)\)", original)
            if target == "INSPECTION_INFO_RECORD" and name == "chk_dt":
                kind = mysql.DATETIME()
            elif length:
                kind = Text() if int(length[1]) > 255 else String(int(length[1]))
            elif original.startswith("datetimev2"):
                kind = mysql.DATETIME(fsp=int(re.search(r"\((\d+)\)", original)[1]))
            else:
                kind = {"text": Text, "int": Integer, "bigint": BigInteger, "tinyint": mysql.TINYINT}[original]()
            comment = item["Comment"] or ""
            if (isinstance(kind, Text) and length) or name == "chk_dt":
                local_type = str(kind.compile(dialect=mysql.dialect()))
                changes.append({"table": target, "field": name, "source_type": original, "local_type": local_type})
            default = item["Default"]
            table.append_column(
                Column(
                    name,
                    kind,
                    nullable=item["Null"] == "YES",
                    comment=comment or None,
                    server_default=text(default) if default is not None else None,
                    primary_key=target == "INSPECTION_INFO_RECORD"
                    and name in {"organ_code", "system_id", "ris_study_id"},
                )
            )
            if isinstance(kind, Text) and length:
                table.append_constraint(CheckConstraint(f"CHAR_LENGTH(`{name}`) <= {int(length[1])}"))
        table.append_column(
            Column(
                "link_id",
                String(512),
                nullable=False,
                comment="MD5 of organ_code + '_' + system_id + '_' + ris_study_id, UTF-8 lowercase hex",
            )
        )
        if target == "SERIES_INFO":
            table.append_column(
                Column(
                    "global_id",
                    String(512),
                    primary_key=True,
                    comment="Synthetic image API series_id; independent of the study link_id",
                )
            )
        else:
            table.append_column(
                Column("EXAM_PART", String(128), comment="WS/T 364.8-2023 CV04.30.002 检查技术编码;一个原始代码")
            )
        tables[target] = table
    return tables, changes


def rows_for(tables):
    from langflow.business.core_flow_demo import image_rows, inspection_cases

    result = {name: [] for name in tables}
    for case in inspection_cases():
        joint = case["joint"]
        part, name = ("髋关节", "模拟患者甲") if joint == "HIP" else ("膝关节", "模拟患者乙")
        common = {
            "organ_code": HOSPITAL,
            "system_id": SYSTEM,
            "ris_study_id": case["study_id"],
            "link_id": link_id(HOSPITAL, SYSTEM, case["study_id"]),
            "chk_modality": case["modality"],
        }
        inspection = dict.fromkeys(tables["INSPECTION_INFO_RECORD"].c.keys())
        inspection.update(
            common,
            organ_name="核心流程模拟医院",
            rpt_no=f"MOCK-RPT-{joint}",
            chk_dt=datetime(2025, 8, 19, 10, tzinfo=ZoneInfo("Asia/Shanghai")).replace(tzinfo=None),
            name=name,
            system_patient_id=f"MOCK-CLOUD-PATIENT-{joint}",
            cardno=f"MOCK-CARD-{joint}",
            op_em_hp_ex_mark=3 if joint == "HIP" else 1,
            op_em_hp_ex_no=f"MOCK-VISIT-{joint}",
            EXAM_PART=case["code"],
            chk_desc=case["description"],
            proj_name=case["description"],
            ckpt_name=part,
            img_count=len(image_rows(case["series_id"])),
            disable_flag=0,
            collect_flag=0,
            center_flag=0,
        )
        series = dict.fromkeys(tables["SERIES_INFO"].c.keys())
        series.update(
            common,
            pacs_series_id=f"MOCK-PACS-SERIES-{joint}{case['suffix']}",
            pacs_study_id=f"MOCK-PACS-STUDY-{joint}{case['suffix']}",
            global_id=case["series_id"],
            patient_id=f"MOCK-CLOUD-PATIENT-{joint}",
            patient_name=name,
            series_number="1",
        )
        result["INSPECTION_INFO_RECORD"].append(inspection)
        result["SERIES_INFO"].append(series)
    return result


def seed(mysql_engine, pg_engine, tables, rows):
    for table in tables.values():
        table.create(mysql_engine, checkfirst=True)
        actual = {c["name"]: c for c in inspect(mysql_engine).get_columns(table.name)}
        if table.name == "INSPECTION_INFO_RECORD" and "EXAM_PART" not in actual:
            with mysql_engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE INSPECTION_INFO_RECORD ADD COLUMN EXAM_PART VARCHAR(128) "
                        "COMMENT 'WS/T 364.8-2023 CV04.30.002 检查技术编码;一个原始代码'"
                    )
                )
            actual = {c["name"]: c for c in inspect(mysql_engine).get_columns(table.name)}
        if set(actual) != set(table.c.keys()):
            msg = f"Existing {table.name} differs; refusing to replace it"
            raise ValueError(msg)
        for name in ("link_id", "global_id"):
            if name in actual and getattr(actual[name]["type"], "length", None) != 512:
                msg = f"Refresh {table.name}.{name} explicitly before seeding"
                raise ValueError(msg)
    with mysql_engine.begin() as db:
        for name, table in tables.items():
            for row in rows[name]:
                query = select(table).where(*(c == row[c.name] for c in table.primary_key))
                existing = db.execute(query).mappings().one_or_none()
                if existing is None:
                    db.execute(table.insert().values(row))
                elif dict(existing) != row:
                    # Only the explicitly owned synthetic identities above are refreshed.
                    db.execute(table.update().where(*(c == row[c.name] for c in table.primary_key)).values(row))
    with pg_engine.begin() as db:
        db.execute(text('ALTER TABLE public.core_flow_settlement_v1 ADD COLUMN IF NOT EXISTS "SYSTEM_ID" VARCHAR(16)'))
        for joint in ("HIP", "KNEE"):
            current = db.execute(
                text(
                    'SELECT "SYSTEM_ID", "RPT_NO" FROM public.core_flow_settlement_v1 '
                    'WHERE "ORGAN_CODE"=:hospital AND "DATA_SOURCE"=:source '
                    'AND "SETL_FEE_LIST_ID"=:detail'
                ),
                {"hospital": HOSPITAL, "source": "MOCK-HIS01", "detail": f"MOCK-DETAIL-{joint}"},
            ).one()
            if current[0] not in {None, SYSTEM} or current[1] not in {None, f"MOCK-RPT-{joint}"}:
                msg = "Settlement links were edited; preserving existing values"
                raise ValueError(msg)
            db.execute(
                text(
                    'UPDATE public.core_flow_settlement_v1 SET "SYSTEM_ID"=:system, "RPT_NO"=:rpt '
                    'WHERE "ORGAN_CODE"=:hospital AND "DATA_SOURCE"=:source AND "SETL_FEE_LIST_ID"=:detail'
                ),
                {
                    "system": SYSTEM,
                    "rpt": f"MOCK-RPT-{joint}",
                    "hospital": HOSPITAL,
                    "source": "MOCK-HIS01",
                    "detail": f"MOCK-DETAIL-{joint}",
                },
            )
        db.execute(text('ALTER TABLE public.core_flow_settlement_v1 ALTER COLUMN "SYSTEM_ID" SET NOT NULL'))
        db.execute(
            text(
                'COMMENT ON COLUMN public.core_flow_settlement_v1."SYSTEM_ID" IS '
                "'检查所属系统的院内唯一ID; 最大16字符; 用户2026-10-13补充; 不替代DATA_SOURCE'"
            )
        )


def call(http, method, path, **kwargs):
    response = http.request(method, path, **kwargs)
    if not response.is_success:
        msg = f"{method} {path}: HTTP {response.status_code}"
        raise RuntimeError(msg)
    return response.json()


def verify(mysql_engine, pg_engine, password, private):
    from langflow.business.core_flow_demo import image_rows, inspection_cases

    with pg_engine.connect() as db:
        settlements = [
            dict(r)
            for r in db.execute(
                text(
                    'SELECT "ORGAN_CODE", "SYSTEM_ID", "RPT_NO", '
                    '"SETL_FEE_LIST_ID" FROM public.core_flow_settlement_v1 WHERE "ORGAN_CODE"=:hospital'
                ),
                {"hospital": HOSPITAL},
            ).mappings()
        ]
    joined = []
    with mysql_engine.connect() as db:
        for settlement in settlements:
            matched = (
                db.execute(
                    text(
                        "SELECT i.rpt_no, i.ris_study_id, i.chk_dt, i.link_id AS inspection_link_id, "
                        "s.link_id AS series_link_id, s.global_id FROM INSPECTION_INFO_RECORD i "
                        "JOIN SERIES_INFO s ON i.organ_code=s.organ_code AND i.system_id=s.system_id "
                        "AND i.ris_study_id=s.ris_study_id "
                        "WHERE i.organ_code=:ORGAN_CODE AND i.system_id=:SYSTEM_ID AND i.rpt_no=:RPT_NO "
                        "AND i.chk_dt BETWEEN '2025-08-01 00:00:00' AND '2025-08-31 23:59:59'"
                    ),
                    settlement,
                )
                .mappings()
                .all()
            )
            expected_count = sum(
                c["joint"] == settlement["SETL_FEE_LIST_ID"].removeprefix("MOCK-DETAIL-") for c in inspection_cases()
            )
            assert len(matched) == expected_count, "Expected the configured synthetic checks per settlement"
            joined.extend(dict(row) for row in matched)
        for name in ("INSPECTION_INFO_RECORD", "SERIES_INFO"):
            count = db.scalar(
                text(
                    f"SELECT COUNT(*) FROM `{name}` WHERE link_id <> "  # noqa: S608 - fixed local table names above.
                    "MD5(CONCAT(organ_code, '_', system_id, '_', ris_study_id))"
                )
            )
            assert count == 0, "Database MD5 check failed"
        assert len(joined) == len(inspection_cases())
        assert all(row["inspection_link_id"] == row["series_link_id"] for row in joined)
        assert len({row["global_id"] for row in joined}) == len(inspection_cases())
    token = private.get("VERIFICATION_IMAGING_TOKEN") or private["VERIFICATION_UPSTREAM_TOKEN"]
    with httpx.Client(base_url="http://127.0.0.1:8091", headers={"X-Token": token}, timeout=30) as http:
        images = [
            call(
                http,
                "GET",
                "/api/v2/storage/dicom/sop-instance-uid",
                params={"series_id": row["global_id"], "url_type": "3"},
            )
            for row in joined
        ]
        assert all(
            result["code"] == 200
            and result["error"]["error_code"] == 0
            and len(result["data"]) == len(image_rows(row["global_id"]))
            for result, row in zip(images, joined, strict=True)
        )
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=120) as http:
        login = call(
            http,
            "POST",
            "/api/v1/login",
            data={"username": "verification-admin", "password": private["LANGFLOW_SUPERUSER_PASSWORD"]},
        )
        http.headers["Authorization"] = "Bearer " + login["access_token"]
        existing = call(http, "GET", "/api/v1/business/connections")
        connection = next((c for c in existing if c["name"] == CONNECTION_NAME), None)
        if connection is None:
            connection = call(
                http,
                "POST",
                "/api/v1/business/connections",
                json={
                    "name": CONNECTION_NAME,
                    "kind": "mysql",
                    "config": {
                        "host": "127.0.0.1",
                        "port": 13306,
                        "database": "business_demo",
                        "username": "business_demo",
                    },
                    "secret": password,
                },
            )
        schemas = {}
        for name, expected in [("INSPECTION_INFO_RECORD", 95), ("SERIES_INFO", 164)]:
            schema = call(
                http, "GET", f"/api/v1/business/connections/{connection['id']}/schema", params={"table": name}
            )
            assert len(schema["fields"]) == expected
            schemas[name] = schema
        schemas["core_flow_settlement_v1"] = call(
            http,
            "GET",
            f"/api/v1/business/connections/{PG_CONNECTION}/schema",
            params={"table": "core_flow_settlement_v1", "schema": "public"},
        )
        assert len(schemas["core_flow_settlement_v1"]["fields"]) == 51
    dump(OUTPUT / "platform-schema.json", schemas)
    return {
        "verified_at": datetime.now().astimezone().isoformat(),
        "simulated": True,
        "connection_id": connection["id"],
        "connection_name": CONNECTION_NAME,
        "field_counts": {name: len(value["fields"]) for name, value in schemas.items()},
        "settlement_count": len(settlements),
        "joined_check_series_count": len(joined),
        "image_count": sum(len(r["data"]) for r in images),
        "links": joined,
        "md5_verified_in_mysql": True,
        "workflow_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    tables, changes = definitions()
    rows = rows_for(tables)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        ddl = str(CreateTable(table, if_not_exists=True).compile(dialect=mysql.dialect()))
        (OUTPUT / f"{name}.sql").write_text("\n".join(line.rstrip() for line in ddl.strip().splitlines()) + ";\n")
    dump(OUTPUT / "rows.json", {"simulated": True, "timezone": "Asia/Shanghai", "tables": rows})
    dump(OUTPUT / "type-adaptations.json", changes)
    if not args.apply:
        print("Generated DDL and synthetic rows; databases unchanged")
        return
    private = dotenv_values(ROOT / "deploy/verification/.env")
    password = dotenv_values(ROOT / "deploy/verification/.cache/business-sources.env")["BUSINESS_DB_PASSWORD"]
    engines = [
        create_engine(
            URL.create(
                driver,
                username="business_demo",
                password=password,
                host="127.0.0.1",
                port=port,
                database="business_demo",
            ),
            hide_parameters=True,
        )
        for driver, port in [("mysql+pymysql", 13306), ("postgresql+psycopg", 55434)]
    ]
    try:
        seed(*engines, tables, rows)
        report = verify(*engines, password, private)
        dump(OUTPUT / "preparation-report.json", report)
        print(json.dumps({k: v for k, v in report.items() if k != "links"}, ensure_ascii=False))
    finally:
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
