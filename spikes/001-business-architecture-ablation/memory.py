"""Fresh-process control/ablation: identical DatasetStore writes, only input materialization differs."""

import hashlib
import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
from langflow.business.datasets import DatasetStore
from langflow.business.models import initialize
from langflow.verification.database import Database

mode, count = sys.argv[1], int(sys.argv[2])
with tempfile.TemporaryDirectory(prefix="langflow-memory-ablation-") as temporary:
    root = Path(temporary)
    os.environ["BUSINESS_DATA_DIR"] = str(root / "datasets")
    db = Database(f"sqlite:///{root}/metadata.db")
    db.initialize()
    initialize(db)
    store = DatasetStore(db, str(uuid4()))
    schema = pa.schema([("sequence", pa.int64()), ("evidence", pa.string())])
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    started = time.perf_counter()

    def batches():
        for start in range(0, count, 5000):
            yield [
                {"sequence": i, "evidence": str(i).zfill(20) + "x" * 108}
                for i in range(start, min(start + 5000, count))
            ]

    if mode == "batched":
        rows = batches()
    else:
        materialized = [row for batch in batches() for row in batch]
        rows = (materialized[start : start + 5000] for start in range(0, count, 5000))
    ref = store.write_batches("Source", rows, schema)
    with store.engine() as engine:
        checksum = engine.execute(f"SELECT SUM(sequence) FROM {store.relation(ref['id'])}").fetchone()[0]
    elapsed = time.perf_counter() - started
    with store.path(ref["id"]).open("rb") as artifact:
        digest = hashlib.file_digest(artifact, "sha256").hexdigest()
    print(
        json.dumps(
            {
                "mode": mode,
                "count": ref["row_count"],
                "sum": int(checksum),
                "seconds": round(elapsed, 3),
                "parquet_sha256": digest,
                "baseline_peak_rss_mib": round(baseline_rss, 1),
                "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                "parquet_bytes": store.path(ref["id"]).stat().st_size,
            }
        )
    )
    db.engine.dispose()
