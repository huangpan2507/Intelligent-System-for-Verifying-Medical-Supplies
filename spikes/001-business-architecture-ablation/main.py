"""Isolated, executable architecture review; never modifies production modules or data."""

import argparse
import asyncio
import copy
import inspect
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
import pyarrow as pa
from langflow.business import api, compiler, relational, runtime, sources
from langflow.business.datasets import ROW_ID, DatasetStore
from langflow.business.models import Dataset, Release, Scheme, Task, initialize
from langflow.verification.api import create_app
from langflow.verification.database import Database, fingerprint
from langflow.verification.settings import VerificationSettings
from sqlalchemy import select

OWNER = "c23d7b4c-e0c9-4eee-a09c-35a8dfd7c7f4"
RESULTS = []


def record(case, kind, mechanism, baseline, intervention, conclusion):
    item = dict(
        case=case, kind=kind, mechanism=mechanism, baseline=baseline, intervention=intervention, conclusion=conclusion
    )
    RESULTS.append(item)
    print(json.dumps(item, ensure_ascii=False, default=str), flush=True)


def mutant(function, old, new, **extra_globals):
    """Change exactly one specified source fragment in memory, with a uniqueness guard."""
    source = textwrap.dedent(inspect.getsource(function))
    assert source.count(old) == 1, (function.__name__, old)
    namespace = {**function.__globals__, **extra_globals}
    exec(compile(source.replace(old, new), "<isolated-ablation>", "exec"), namespace)
    return namespace[function.__name__]


class Lab:
    def __init__(self, root):
        os.environ["BUSINESS_DATA_DIR"] = str(root / "datasets")
        os.environ["LANGFLOW_CONFIG_DIR"] = str(root / "platform")
        self.db = Database(f"sqlite:///{root}/experiment.db")
        self.db.initialize()
        initialize(self.db)
        self.settings = VerificationSettings(
            database_url=f"sqlite:///{root}/experiment.db",
            clients={"a": "a" * 20, "b": "b" * 20},
            internal_token="i" * 20,
            langflow_api_key="l" * 20,
            demo_mode=True,
        )
        self.store = DatasetStore(self.db, str(uuid4()))

    def write(self, rows, schema, name="source", batches=None):
        return self.store.write_batches(name, batches if batches is not None else [rows], schema)

    def unary(self, kind, config, ref, source=None):
        queries = relational.unary_query(
            kind, config, source or self.store.relation(ref["id"]), relational.fields_of(ref)
        )
        return {port: self.store.query(kind, sql, port=port, parents=[ref["id"]]) for port, sql in queries.items()}

    def rows(self, ref):
        assert ref["row_count"] <= 1000, "Use this helper only for small correctness fixtures"
        return self.store.page(ref["id"], limit=1000)["rows"]

    def graph(self):
        file_id = str(uuid4())
        path = sources.file_path(OWNER, file_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("code,value,extra\nA,1,preserved\nB,2,preserved\n")
        return {
            "nodes": [
                {
                    "id": "Source",
                    "kind": "file",
                    "config": {
                        "file_id": file_id,
                        "format": "csv",
                        "fields": [
                            {"name": "code", "type": "text"},
                            {"name": "value", "type": "integer"},
                            {"name": "extra", "type": "text"},
                        ],
                    },
                },
                {"id": "Result", "kind": "output", "config": {"name": "Results", "columns": ["code", "value"]}},
            ],
            "edges": [{"source": "Source", "target": "Result", "port": "data", "input": "data"}],
        }

    def release(self, graph, code=None, version=1):
        package = compiler.inspect_graph(graph, self.db, self.settings, OWNER)
        code = code or "case-" + str(uuid4())
        with self.db.sessions.begin() as session:
            row = Release(scheme_code=code, version=version, package=package, content_hash=fingerprint(package))
            session.add(row)
            session.flush()
            scheme = session.get(Scheme, code)
            if scheme is None:
                scheme = Scheme(
                    code=code, name=code, owner_id=OWNER, flow_id=str(uuid4()), draft=graph, allowed_sources=["a"]
                )
                session.add(scheme)
            scheme.active_release_id = row.id
        return row

    def task(self, release):
        with self.db.sessions.begin() as session:
            task = Task(
                owner_id=OWNER,
                source="a",
                idempotency_key=str(uuid4()),
                content_hash="x",
                scheme_code=release.scheme_code,
                release_id=release.id,
                parameters={},
            )
            session.add(task)
            session.flush()
        return task

    def task_result(self, task):
        with self.db.sessions() as session:
            row = session.get(Task, task.id)
            store = DatasetStore(self.db, row.id)
            return {"status": row.status, "rows": store.page(row.results[0])["rows"]}


def relational_cases(lab):
    ref = lab.write([{"paid": True}, {"paid": False}, {"paid": None}], pa.schema([("paid", pa.bool_())]))
    cfg = {"conditions": [{"field": "paid", "op": "eq", "value": True}]}
    before = {p: r["row_count"] for p, r in lab.unary("filter", cfg, ref).items()}
    original = relational.predicate
    with patch.object(relational, "predicate", lambda *args: f"coalesce(({original(*args)}), FALSE)"):
        after = {p: r["row_count"] for p, r in lab.unary("filter", cfg, ref).items()}
    assert before == {"matched": 1, "unmatched": 1, "unknown": 1}
    assert after == {"matched": 1, "unmatched": 2, "unknown": 0}
    record("A01", "ablation", "三态筛选", before, after, "将 NULL 当作 false 会把未知事实误判为明确不符合范围。")

    left = lab.write(
        [{"key": "A", "amount": 100}, {"key": "A", "amount": 100}],
        pa.schema([("key", pa.string()), ("amount", pa.int64())]),
    )
    right = lab.write([{"key": "A", "amount": 100}], pa.schema([("key", pa.string()), ("amount", pa.int64())]))
    counts = []
    for cardinality in ["one_to_one", "many_to_many"]:
        queries = relational.join_queries(
            {"keys": [{"left": "key", "right": "key"}], "cardinality": cardinality},
            lab.store.relation(left["id"]),
            lab.store.relation(right["id"]),
            relational.fields_of(left),
            relational.fields_of(right),
        )
        refs = {p: lab.store.query("join", q, port=p) for p, q in queries.items()}
        compared = lab.unary(
            "compare", {"comparisons": [{"left": "left_amount", "right": "right_amount"}]}, refs["data"]
        )
        counts.append(
            {
                "result_rows": refs["data"]["row_count"],
                "issues": refs["issues"]["row_count"],
                "equal_rows": sum(r["_comparison_status"] == "equal" for r in lab.rows(compared["data"])),
            }
        )
    assert counts == [
        {"result_rows": 0, "issues": 3, "equal_rows": 0},
        {"result_rows": 2, "issues": 0, "equal_rows": 2},
    ]
    record(
        "A02",
        "ablation",
        "关联匹配关系约束",
        *counts,
        "同一夹具业务要求一对一；去掉唯一性约束后出现两条伪正常匹配。多对多在其他业务中可以合法。",
    )

    schema = pa.schema([("key", pa.string()), ("amount", pa.int64())])
    batches = [[{"key": "A", "amount": 60}], [{"key": "A", "amount": 40}]]
    ref = lab.write([], schema, batches=batches)
    cfg = {"group_by": ["key"], "metrics": [{"field": "amount", "operation": "sum", "output": "total"}]}
    before = [r["total"] for r in lab.rows(lab.unary("aggregate", cfg, ref)["data"])]
    after = []
    for batch in batches:
        after += [r["total"] for r in lab.rows(lab.unary("aggregate", cfg, lab.write(batch, schema))["data"])]
    assert list(map(Decimal, before)) == [100] and list(map(Decimal, after)) == [60, 40]
    record(
        "A03",
        "ablation",
        "跨批次全局汇总",
        before,
        after,
        "分批仅是物理取数策略，不能成为业务分组边界。局部汇总后还须全局归并。",
    )

    ref = lab.write(
        [{"a": Decimal("9007199254740992.01"), "b": Decimal("9007199254740992.02")}],
        pa.schema([("a", pa.decimal128(38, 2)), ("b", pa.decimal128(38, 2))]),
    )
    cfg = {"comparisons": [{"left": "a", "right": "b", "mode": "numeric"}]}
    before = lab.rows(lab.unary("compare", cfg, ref)["data"])[0]
    source = f'(SELECT CAST(a AS DOUBLE) AS a, CAST(b AS DOUBLE) AS b, "{ROW_ID}" FROM {lab.store.relation(ref["id"])})'
    after = lab.rows(lab.unary("compare", cfg, ref, source=source)["data"])[0]
    assert before["_comparison_status"] == "different" and after["_comparison_status"] == "equal"
    record(
        "A04",
        "ablation",
        "精确数值",
        before,
        after,
        "极值夹具中浮点数吞掉 0.01 差异；证明数值表示有约束，不代表所有金额范围均失败。",
    )

    ref = lab.write(
        [{"key": "A", "amount": 100, "unused_evidence": "original note"}],
        pa.schema([("key", pa.string()), ("amount", pa.int64()), ("unused_evidence", pa.string())]),
    )
    output = lab.unary("output", {"columns": ["key", "amount"]}, ref)["data"]
    before = {"output": lab.rows(output), "raw_evidence_available": lab.store.path(ref["id"]).exists()}
    lab.store.path(ref["id"]).unlink()  # Only this experiment's temporary snapshot.
    after = {"output": lab.rows(output), "raw_evidence_available": lab.store.path(ref["id"]).exists()}
    assert before["output"] == after["output"] and not after["raw_evidence_available"]
    record(
        "A05",
        "ablation",
        "原始快照留存",
        before,
        after,
        "数值结果不变，但未参与计算的证据不可追溯；快照的必要性来自审计要求。",
    )


async def lifecycle_cases(lab):
    graph = lab.graph()
    release1 = lab.release(graph)
    baseline, ablated = lab.task(release1), lab.task(release1)
    graph2 = copy.deepcopy(graph)
    graph2["nodes"].append(
        {"id": "OnlyB", "kind": "filter", "config": {"conditions": [{"field": "code", "op": "eq", "value": "B"}]}}
    )
    graph2["edges"] = [
        {"source": "Source", "target": "OnlyB", "port": "data", "input": "data"},
        {"source": "OnlyB", "target": "Result", "port": "matched", "input": "data"},
    ]
    lab.release(graph2, code=release1.scheme_code, version=2)
    await runtime.run_task(lab.db, lab.settings, baseline.id)
    changed = mutant(
        runtime.run_task,
        "release = session.get(Release, task.release_id)",
        "release = session.get(Release, session.get(Scheme, task.scheme_code).active_release_id)",
        Scheme=Scheme,
    )
    await changed(lab.db, lab.settings, ablated.id)
    before, after = lab.task_result(baseline), lab.task_result(ablated)
    assert len(before["rows"]) == 2 and len(after["rows"]) == 1
    record(
        "A06",
        "ablation",
        "受理版本固定",
        before,
        after,
        "受理同为 v1；只把执行时的版本来源改为当前启用版本，就丢掉 A 行。",
    )

    changed = mutant(api.register, " or (source and task.source != source)", "")
    statuses = []
    for replacement in [api.register, changed]:
        with patch.object(api, "register", replacement):
            app = create_app(lab.settings, lab.db)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get(
                f"/api/v1/business/tasks/{baseline.id}", headers={"Authorization": "Bearer " + "b" * 20}
            )
            statuses.append(response.status_code)
    assert statuses == [404, 200]
    record(
        "A07",
        "ablation",
        "结果来源隔离",
        statuses[0],
        statuses[1],
        "真实 ASGI 查询；移除 task.source 判定后，来源 B 能读取来源 A 的任务。",
    )

    release = lab.release(lab.graph())
    task = lab.task(release)
    with patch.object(runtime, "file_read", wraps=runtime.file_read) as counted:
        await runtime.run_task(lab.db, lab.settings, task.id)
        try:
            await runtime.run_task(lab.db, lab.settings, task.id)
        except ValueError as exc:
            assert "already started" in str(exc)
        else:
            raise AssertionError("Second execution was not rejected")
        before = counted.call_count
        changed = mutant(runtime.run_task, 'if task.started or task.status not in {"waiting", "running"}:', "if False:")
        await changed(lab.db, lab.settings, task.id)
        after = counted.call_count
    assert before == 1 and after == 2
    record(
        "A08",
        "ablation",
        "已启动任务重入拦截",
        before,
        after,
        "移除入口状态拦截后，相同任务重做取数。此实验不证明分布式 exactly-once 或远端模型幂等。",
    )

    task = lab.task(release)
    original = Path.read_bytes
    target = Path(compiler.__file__).with_name("demo.py")

    def changed_bytes(path):
        content = original(path)
        return content + b"\n# unrelated demo comment\n" if path == target else content

    before = compiler.runtime_digest()
    with patch.object(Path, "read_bytes", changed_bytes):
        after = compiler.runtime_digest()
        try:
            await runtime.run_task(lab.db, lab.settings, task.id)
        except ValueError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected broad fingerprint to block execution")
    assert before != after and "runtime differs" in message
    record(
        "C01",
        "counterexample",
        "运行版本校验边界",
        {"unmodified_digest": before},
        {"comment_only_digest": after, "blocked": message},
        "只在内存模拟 demo.py 增加注释，文件不落盘；无关演示代码也阻断已发布任务。需要缩小构建依赖边界或保留旧运行包，不应删除版本约束。",
    )

    graph = lab.graph()
    graph["nodes"].append(
        {"id": "OnlyA", "kind": "filter", "config": {"conditions": [{"field": "code", "op": "eq", "value": "A"}]}}
    )
    graph["edges"] = [
        {"source": "Source", "target": "OnlyA", "port": "data", "input": "data"},
        {"source": "OnlyA", "target": "Result", "port": "matched", "input": "data"},
    ]
    task = lab.task(lab.release(graph))
    await runtime.run_task(lab.db, lab.settings, task.id)
    result = lab.task_result(task)
    with lab.db.sessions() as session:
        leftovers = session.scalars(
            select(Dataset).where(Dataset.task_id == task.id, Dataset.port == "unmatched")
        ).all()
    assert result["status"] == "completed" and len(result["rows"]) == 1 and leftovers[0].row_count == 1
    record(
        "C02",
        "counterexample",
        "最终业务覆盖核对",
        {"baseline_detail_ids": ["A", "B"]},
        {**result, "unmatched_persisted": 1, "final_disposition_missing": ["B"]},
        "图合法且任务完成，中间快照保留 B，但最终业务去向未声明。本夹具要求两行均有去向；普通筛选业务只输出 A 可以合法，平台须让方案声明覆盖契约。",
    )

    graph = lab.graph()
    release = lab.release(graph)
    source_config = graph["nodes"][0]["config"]
    sources.file_path(OWNER, source_config["file_id"]).write_text(
        "code,value,extra\nA,one,preserved\nB,two,preserved\n"
    )
    baseline, ablated = lab.task(release), lab.task(release)
    try:
        await runtime.run_task(lab.db, lab.settings, baseline.id)
    except Exception:
        with lab.db.sessions() as session:
            before = session.get(Task, baseline.id).status
        assert before == "failed"
    else:
        raise AssertionError("Changed source type was not rejected")
    changed = mutant(sources.file_read, "if actual_type not in accepted_types:", "if False:")
    with patch.object(runtime, "file_read", changed):
        await runtime.run_task(lab.db, lab.settings, ablated.id)
    after = lab.task_result(ablated)
    assert after["status"] == "completed" and {r["value"] for r in after["rows"]} == {"one", "two"}
    record(
        "A12",
        "ablation",
        "运行时字段类型契约",
        before,
        after,
        "发布时 value 为整数，运行前改成文本；移除读取器类型检查后，任务完成并输出与发布声明不符的字段。使用文件隔离复现，未替代数据库字段漂移测试。",
    )


def parameter_case():
    import jsonschema
    from langflow.business.contracts import normalize_parameters

    specs = [{"name": "days", "type": "integer", "required": True}]
    supplied = {"days": "not-an-integer", "unexpected_connection": "outside"}
    try:
        normalize_parameters(specs, supplied)
    except jsonschema.ValidationError:
        before = "rejected"
    else:
        raise AssertionError("Invalid external parameters accepted")
    with patch.object(jsonschema, "validate", return_value=None):
        after = normalize_parameters(specs, supplied)
    assert after == supplied
    record(
        "A13",
        "ablation",
        "声明式任务参数契约",
        before,
        after,
        "删除参数结构校验后，错误类型和未声明字段进入任务参数。未声明字段被接收不等于它已获得修改数据库连接的能力。",
    )


async def scheduler_case(lab):
    from langflow.business.templates import comparison

    graph = comparison()
    fixtures = {
        "Orders": "order_no,amount\nA,100\nB,200\nC,300\n",
        "Payments": "payment_id,biz_no,amount\nP1,A,60\nP2,A,40\nP3,B,180\nP4,D,50\n",
    }
    for node in graph["nodes"]:
        if node["id"] in fixtures:
            file_id = str(uuid4())
            path = sources.file_path(OWNER, file_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixtures[node["id"]])
            node["kind"] = "file"
            node["config"] = {
                "file_id": file_id,
                "format": "csv",
                "fields": [
                    {"name": field, "type": "integer" if field == "amount" else "text"}
                    for field in fixtures[node["id"]].splitlines()[0].split(",")
                ],
            }
    release = lab.release(graph)
    changed = mutant(
        runtime.Runtime.execute,
        'source = (await self.execute(edge["source"]))[edge["port"]]',
        'source = self.outputs[edge["source"]][edge["port"]]',
    )
    measurements = []
    for execute in [runtime.Runtime.execute, changed]:
        task = lab.task(release)
        with (
            patch.object(runtime.Runtime, "execute", execute),
            patch.object(runtime, "file_read", wraps=runtime.file_read) as reads,
        ):
            await runtime.run_task(lab.db, lab.settings, task.id)
            calls = reads.call_count
        with lab.db.sessions() as session:
            saved = session.get(Task, task.id)
            result_ids = saved.results
            completed = sum(p["status"] == "completed" for p in saved.progress.values())
        outputs = []
        for dataset_id in result_ids:
            rows = DatasetStore(lab.db, task.id).page(dataset_id)["rows"]
            outputs.append(
                sorted(json.dumps({k: v for k, v in row.items() if "row_id" not in k}, sort_keys=True) for row in rows)
            )
        measurements.append({"outputs": outputs, "source_reads": calls, "completed_nodes": completed})
    assert measurements[0] == measurements[1]
    assert measurements[0]["source_reads"] == 2 and measurements[0]["completed_nodes"] == len(graph["nodes"])
    record(
        "A14",
        "ablation",
        "双重图遍历中的递归回溯",
        *measurements,
        "保留 Langflow 图调度，只把 Runtime 的递归找前驱改为读取已完成前驱输出；带分支、汇总、关联和多结果的对账图结果相同，两源各读取一次。支持删除重复依赖遍历；未证明所有子流程/并发/失败恢复场景等价。",
    )


def union_counterexample(lab):
    schema = pa.schema([("uid", pa.string()), ("patient", pa.string())])
    first = lab.write([{"uid": "same-uid", "patient": "patient-A"}], schema)
    second = lab.write([{"uid": "same-uid", "patient": "patient-B"}], schema)
    executor = runtime.Runtime(
        lab.db,
        lab.settings,
        SimpleNamespace(id=lab.store.task_id, parameters={}),
        {"graph": {"nodes": [], "edges": []}},
    )
    node = {"id": "Union", "kind": "union", "config": {"deduplicate": True, "keys": ["uid"]}}
    original = lab.rows(executor.run_node(node, {"data": [first, second]})["data"])
    # Swap opaque dataset IDs while preserving the same set of business records.
    p1, p2 = lab.store.path(first["id"]), lab.store.path(second["id"])
    a, b = p1.read_bytes(), p2.read_bytes()
    try:
        p1.write_bytes(b)
        p2.write_bytes(a)
        swapped = lab.rows(executor.run_node(node, {"data": [first, second]})["data"])
    finally:
        p1.write_bytes(a)
        p2.write_bytes(b)
    assert original[0]["patient"] != swapped[0]["patient"]
    record(
        "C03",
        "counterexample",
        "按键去重时的冲突语义",
        original,
        swapped,
        "同 UID 关联不同患者，当前按数据集 UUID 保留一条。两份原始记录仍在，但没有冲突输出；换无业务含义的 ID 会改变被采信患者。",
    )


def model_cases(lab):
    schema = pa.schema(
        [
            ("patient", pa.string()),
            ("hospital", pa.string()),
            ("encounter", pa.string()),
            ("category", pa.string()),
            ("quantity", pa.int64()),
            ("unit", pa.string()),
        ]
    )
    ref = lab.write([dict(patient="P", hospital="H", encounter="E", category="hip", quantity=1, unit="set")], schema)
    connection = SimpleNamespace(id="synthetic-model", config={"base_url": "http://model.invalid"}, secret="")
    config = {"path": "/analyze", **{f + "_field": f for f in schema.names}}
    body = dict(
        recognized_quantity=1,
        observed_unit="set",
        coverage_confirmed=False,
        recognition_confirmed=True,
        evidence_ref="synthetic-evidence",
        simulated=True,
    )

    def run(response_body, function=sources.model_read, refs_only=False):
        client = httpx.Client(
            base_url="http://model.invalid",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response_body)),
        )
        with patch.dict(function.__globals__, {"client_for": lambda *args: client}):
            refs = function(lab.store, "Imaging", config, connection, lab.settings, ref, imaging=True)
            return refs if refs_only else {port: lab.rows(r) for port, r in refs.items()}

    before = run(body)
    changed = mutant(
        sources.model_read,
        'if not response.get("coverage_confirmed") or not response.get("recognition_confirmed"):',
        "if False:",
    )
    after = run(body, changed)
    assert len(before["issues"]) == 1 and len(after["data"]) == 1
    record(
        "A09",
        "ablation",
        "识别与覆盖依据门槛",
        before,
        after,
        "去掉依据判定后覆盖未确认也成为可用数据。证明判定责任不可省，不证明应放在模型调用器内，也不证明两个布尔值足以证明真实可比性。",
    )

    gate = '''                            if not response.get("coverage_confirmed") or not response.get("recognition_confirmed"):
                                issue = "recognition_or_coverage_unconfirmed"
                            elif response.get("observed_unit") != record["unit"]:
                                issue = "counting_unit_mismatch"
                            elif not response.get("evidence_ref"):
                                issue = "missing_recognition_evidence"'''
    ungated = mutant(sources.model_read, gate, "                            pass")
    validation = {
        "conditions": [
            {"field": "coverage_confirmed", "op": "eq", "value": True},
            {"field": "recognition_confirmed", "op": "eq", "value": True},
            {"field": "observed_unit", "op": "eq", "right_field": "unit"},
            {"field": "evidence_ref", "op": "ne", "value": ""},
        ]
    }
    valid = {**body, "coverage_confirmed": True}
    fixtures = [valid, body, {**valid, "observed_unit": "piece"}, {**valid, "evidence_ref": ""}]
    baseline, removed, relocated = [], [], []
    for response in fixtures:
        control = run(response, refs_only=True)
        candidate = run(response, ungated, refs_only=True)
        checked = lab.unary("validate", validation, candidate["data"])
        baseline.append(control["data"]["row_count"])
        removed.append(candidate["data"]["row_count"])
        relocated.append(checked["valid"]["row_count"])
    assert baseline == relocated == [1, 0, 0, 0] and removed == [1, 1, 1, 1]
    record(
        "A11",
        "ablation-and-relocation",
        "调用与业务判定解耦",
        {"usable_rows_per_fixture": baseline},
        {"remove_gate_only": removed, "relocate_to_existing_validate": relocated},
        "有效、覆盖不足、单位不符、无证据四个夹具：判定移到现有 Validate 后有效/无效划分不变。支持抽出纯规则责任；未证明完整医学可比性，未验证新接口协议，原因文案也未要求相同。",
    )

    invalid = run({**valid, "recognized_quantity": -1})
    assert len(invalid["data"]) == 1
    record(
        "C05",
        "counterexample",
        "专业输出有效性",
        {"expected": "negative physical count must be invalid"},
        {"accepted_data_rows": len(invalid["data"]), "recognized_quantity": invalid["data"][0]["recognized_quantity"]},
        "当前 Imaging 接受负的实物识别数量；现有模板没有后置数量非负校验。布尔确认标记与证据引用并不构成完整有效性检查。",
    )

    remote = []

    def accepted_then_timeout(request):
        remote.append({"accepted": True, "remote_job_id": "external-job-1", "payload": json.loads(request.content)})
        raise httpx.ReadTimeout("Synthetic timeout after remote acceptance", request=request)

    with patch.object(
        sources,
        "client_for",
        return_value=httpx.Client(
            base_url="http://model.invalid", transport=httpx.MockTransport(accepted_then_timeout)
        ),
    ):
        refs = sources.model_read(lab.store, "Timeout", config, connection, lab.settings, ref, imaging=True)
    rows = lab.rows(refs["issues"])
    assert len(remote) == 1 and rows[0]["_model_response"] == "{}" and "ReadTimeout" in rows[0]["_issue_reason"]
    record(
        "C04",
        "counterexample",
        "外部模型请求关联",
        {"remote_accepted_count": len(remote)},
        {
            "local_issue": rows[0]["_issue_reason"],
            "saved_response": rows[0]["_model_response"],
            "request_id_sent": "request_id" in remote[0]["payload"],
            "remote_job_id_saved": False,
        },
        "远端受理后响应超时，只保存本地错误，没有提交前的独立请求标识。不能据此判断远端失败，也无法按本次请求查询核实。此为故障注入，不是已实现机制的消融。",
    )


async def main(output, count):
    with tempfile.TemporaryDirectory(prefix="langflow-ablation-") as temporary:
        lab = Lab(Path(temporary))
        try:
            relational_cases(lab)
            parameter_case()
            await lifecycle_cases(lab)
            await scheduler_case(lab)
            union_counterexample(lab)
            model_cases(lab)
        finally:
            lab.db.engine.dispose()
    memory = {mode: [] for mode in ["batched", "materialized"]}
    for size in sorted({min(100_000, count), count}):
        for mode in memory:
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import subprocess, sys; sys.exit(subprocess.call(sys.argv[1:]))",
                    sys.executable,
                    str(Path(__file__).with_name("memory.py")),
                    mode,
                    str(size),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sample = json.loads(child.stdout)
            assert sample["count"] == size and sample["sum"] == size * (size - 1) // 2
            memory[mode].append(sample)
        assert memory["batched"][-1]["parquet_sha256"] == memory["materialized"][-1]["parquet_sha256"]
    record(
        "A10",
        "ablation",
        "分批持久化而非整批 Python 对象",
        memory["batched"],
        memory["materialized"],
        "同一写入器、同一数据、相同 5000 行批次、输出文件 SHA256 相同，只改变是否预先构造全量行列表；峰值 RSS 包含进程基线。此为合成存储实验，不是跨数据库吞吐或真实影像压测。",
    )
    output.write_text(
        json.dumps(
            {
                "cases": RESULTS,
                "case_count": len(RESULTS),
                "production_modified": False,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "runtime_digest": compiler.runtime_digest(),
                "python": sys.version,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(f"Recorded {len(RESULTS)} experiments: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    parser.add_argument("--rows", type=int, default=1_000_000)
    args = parser.parse_args()
    asyncio.run(main(args.output, args.rows))
