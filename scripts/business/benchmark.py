"""Run a reproducible million-row end-to-end graph against persisted Parquet inputs."""

import argparse
import asyncio
import json
import os
import resource
import tempfile
import time
import threading
import platform
from pathlib import Path
from uuid import uuid4

import duckdb
from langflow.business.compiler import inspect_graph
from langflow.business.datasets import DatasetStore, literal
from langflow.business.models import Release, Task, initialize
from langflow.business.runtime import run_task
from langflow.business.sources import file_path
from langflow.business.templates import comparison
from langflow.verification.database import Database, fingerprint
from langflow.verification.settings import VerificationSettings


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--databases", action="store_true", help="Use dedicated MySQL/PostgreSQL sources")
    parser.add_argument("--rows-per-source", type=int, default=500000)
    parser.add_argument("--output", default="deploy/verification/.cache/business-benchmark.json")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="business-benchmark-"))
    os.environ["BUSINESS_DATA_DIR"] = str(root / "data")
    os.environ["LANGFLOW_CONFIG_DIR"] = str(root / "platform")
    db = Database(f"sqlite:///{root}/metadata.db")
    db.initialize()
    initialize(db)
    owner = str(uuid4())
    settings = VerificationSettings(
        database_url=f"sqlite:///{root}/metadata.db",
        internal_token="i" * 20,
        clients={"benchmark": "b" * 20},
        demo_mode=True,
    )
    cleanup = lambda: None
    if args.databases:
        from benchmark_databases import prepare_sources

        graph, cleanup = prepare_sources(db, settings, owner, args.rows_per_source)
    else:
        graph = comparison()
        with duckdb.connect() as sql:
            for node in graph["nodes"]:
                if node["kind"] != "database":
                    continue
                file_id = str(uuid4())
                path = file_path(owner, file_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                if node["id"] == "Orders":
                    query = f"SELECT 'O' || i AS order_no, 100::DECIMAL(18,2) AS amount, 'raw-preserved' AS extra FROM range({args.rows_per_source}) t(i)"
                    fields = [
                        {"name": "order_no", "type": "text"},
                        {"name": "amount", "type": "number"},
                        {"name": "extra", "type": "text"},
                    ]
                else:
                    query = f"SELECT 'P' || i AS payment_id, 'O' || i AS biz_no, (CASE WHEN i % 10000=0 THEN 99 ELSE 100 END)::DECIMAL(18,2) AS amount FROM range({args.rows_per_source}) t(i)"
                    fields = [
                        {"name": "payment_id", "type": "text"},
                        {"name": "biz_no", "type": "text"},
                        {"name": "amount", "type": "number"},
                    ]
                sql.execute(f"COPY ({query}) TO {literal(str(path))} (FORMAT PARQUET)")
                node.update(kind="file", config={"file_id": file_id, "format": "parquet", "fields": fields})
    package = inspect_graph(graph, db, settings, owner)
    with db.sessions.begin() as session:
        release = Release(scheme_code="benchmark", version=1, package=package, content_hash=fingerprint(package))
        session.add(release)
        session.flush()
        task = Task(
            owner_id=owner,
            source="benchmark",
            idempotency_key="million",
            content_hash="fixture",
            scheme_code="benchmark",
            release_id=release.id,
            parameters={},
        )
        session.add(task)
        session.flush()
    start = time.monotonic()
    stop_sampling = threading.Event()
    peak_disk = {"total": 0, "spill": 0}

    def sample_disk():
        while not stop_sampling.is_set():
            total, spill = 0, 0
            for path in root.rglob("*"):
                try:
                    if path.is_file():
                        size = path.stat().st_size
                        total += size
                        if "spill" in path.parts:
                            spill += size
                except FileNotFoundError:
                    pass
            peak_disk["total"] = max(peak_disk["total"], total)
            peak_disk["spill"] = max(peak_disk["spill"], spill)
            stop_sampling.wait(0.1)

    sampler = threading.Thread(target=sample_disk, daemon=True)
    sampler.start()
    try:
        await run_task(db, settings, task.id)
    finally:
        stop_sampling.set()
        sampler.join()
        cleanup()
    elapsed = time.monotonic() - start
    with db.sessions() as session:
        task = session.get(Task, task.id)
    store = DatasetStore(db, task.id)
    with store.engine() as sql:
        from langflow.business.models import Dataset

        with db.sessions() as session:
            result = session.scalar(
                __import__("sqlalchemy")
                .select(Dataset)
                .where(Dataset.task_id == task.id, Dataset.node_id == "Results", Dataset.port == "data")
            )
        counts = dict(
            sql.execute(f"SELECT _comparison_status,count(*) FROM {store.relation(result.id)} GROUP BY 1").fetchall()
        )
    expected = (args.rows_per_source + 9999) // 10000
    assert counts.get("different") == expected, counts
    report = {
        "source_kind": "mysql_postgresql" if args.databases else "parquet",
        "input_rows": args.rows_per_source * 2,
        "output_rows": sum(counts.values()),
        "counts": counts,
        "expected_differences": expected,
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "machine": platform.platform(),
        "batch_size": 5000,
        "peak_disk_mb_sampled": round(peak_disk["total"] / 1024 / 1024, 1),
        "peak_spill_mb_sampled": round(peak_disk["spill"] / 1024 / 1024, 1),
        "disk_sample_interval_seconds": 0.1,
        "runtime_digest": package["runtime_digest"],
        "disk_mb": round(sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) / 1024 / 1024, 1),
        "task_id": task.id,
        "status": task.status,
        "root": str(root),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
