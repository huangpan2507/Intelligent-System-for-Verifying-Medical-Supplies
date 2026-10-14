# ruff: noqa: S608 - SQL uses quoted identifiers/literals and validated operators; source SELECT runs read-only.
"""Execute immutable graph nodes through Langflow, with persistent dataset receipts."""

import asyncio
import copy
import time
from types import SimpleNamespace

from langflow.business.components import ACTIVE_RUNTIME, classes
from langflow.business.connections import read_database
from langflow.business.datasets import ROW_ID, DatasetStore, IncompleteReadError, ident, literal
from langflow.business.models import Connection, Task
from langflow.business.relational import fields_of, identity_queries, join_queries, unary_query
from langflow.business.sources import api_read, bindings, file_read, model_read
from langflow.verification.database import now


class Runtime:
    def __init__(self, database, settings, task, package, *, parameters=None, prefix=""):
        self.database, self.settings, self.task = database, settings, task
        self.package = package
        self.graph = copy.deepcopy(package["graph"])
        from langflow.business.contracts import normalize_parameters

        self.task_input = None
        if package.get("task_input"):
            from langflow.business.task_input import accepted_input

            with database.sessions() as session:
                self.task_input = accepted_input(session, task)
            if self.task_input is None:
                msg = "Regulatory task has no accepted input receipt"
                raise ValueError(msg)
            self.parameters = {**self.task_input["parameters"], **self.task_input["task"]}
        else:
            self.parameters = (
                parameters if parameters is not None else normalize_parameters(package["parameters"], task.parameters)
            )
        self.prefix = prefix
        self.nodes = {n["id"]: n for n in self.graph["nodes"]}
        self.store = DatasetStore(database, task.id)
        self.outputs, self.locks = {}, {}
        self.output_ids = []
        self.failures = {}

    def connection(self, connection_id):
        fixed = self.package["connections"][connection_id]
        with self.database.sessions() as session:
            connection = session.get(Connection, connection_id)
            if connection is None or connection.owner_id != self.task.owner_id:
                msg = "Connection no longer available"
                raise ValueError(msg)
            return SimpleNamespace(**fixed, secret=connection.secret)

    async def execute(self, node_id):
        async with self.locks.setdefault(node_id, asyncio.Lock()):
            if node_id in self.outputs:
                return self.outputs[node_id]
            node = self.nodes[node_id]
            incoming = {}
            for edge in self.graph["edges"]:
                if edge["target"] == node_id:
                    # Langflow owns traversal; output caches share one execution across ports.
                    if edge["source"] not in self.outputs:
                        msg = f"Scheduler did not finish dependency {edge['source']}"
                        raise ValueError(msg)
                    source = self.outputs[edge["source"]][edge["port"]]
                    if source.get("id"):
                        incoming.setdefault(edge["input"], []).append(source)
            started = time.monotonic()
            self.progress(node_id, "running")
            try:
                if node["kind"] == "subflow":
                    config = node["config"]
                    package = self.package["subflows"][config["release_id"]]
                    from langflow.business.contracts import normalize_parameters

                    child_parameters = normalize_parameters(
                        package["parameters"], bindings(config.get("parameters", {}), self.parameters)
                    )
                    child = Runtime(
                        self.database,
                        self.settings,
                        self.task,
                        package,
                        parameters=child_parameters,
                        prefix=self.prefix + node_id + "--",
                    )
                    if incoming.get("data"):
                        child.parameters["dataset"] = incoming["data"][0]
                    await child.run_graph()
                    self.failures.update({node_id + "--" + key: value for key, value in child.failures.items()})
                    outputs = {"data": child.outputs[config["output_node"]]["data"]}
                else:
                    outputs = await asyncio.to_thread(self.run_node, node, incoming)
                if node["kind"] == "database":
                    from langflow.business.compiler import sql_type

                    expected = self.package["schemas"][node_id]["data"]
                    actual = outputs["data"]["fields"]

                    def signature(fields):
                        return [(f["name"], sql_type(f["type"])) for f in fields]

                    if any(item not in signature(actual) for item in signature(expected)):
                        msg = "Database schema changed since publication; rebind and republish"
                        raise ValueError(msg)
            except Exception as exc:  # noqa: BLE001 - Persist node failure and allow independent branches.
                self.failures[node_id] = type(exc).__name__
                self.progress(node_id, "failed", elapsed=time.monotonic() - started, error=type(exc).__name__)
                if isinstance(exc, IncompleteReadError):
                    outputs = {"data": exc.receipt}
                else:
                    from langflow.business.compiler import field_sql_type

                    outputs = {}
                    for port, fields in self.package["schemas"][node_id].items():
                        columns = ", ".join(f"NULL::{field_sql_type(f)} AS {ident(f['name'])}" for f in fields)
                        outputs[port] = self.store.query(
                            self.prefix + node_id,
                            f"SELECT {columns} WHERE FALSE",
                            port=port,
                            details={
                                "completeness": {"state": "incomplete", "error": type(exc).__name__},
                                "operation": "failed",
                                "error": type(exc).__name__,
                            },
                        )
                self.outputs[node_id] = outputs
                return outputs
            else:
                self.outputs[node_id] = outputs
                self.progress(node_id, "completed", outputs, time.monotonic() - started)
                return outputs

    def progress(self, node_id, status, outputs=None, elapsed=None, error=None):
        with self.database.sessions.begin() as session:
            task = session.get(Task, self.task.id, with_for_update=True)
            progress = dict(task.progress)
            progress[self.prefix + node_id] = {
                "status": status,
                "outputs": outputs or {},
                "elapsed_seconds": elapsed,
                "error": error,
            }
            task.progress = progress

    def run_node(self, node, incoming):
        kind, config, node_id = node["kind"], node["config"], self.prefix + node["id"]
        if kind == "taskinput":
            return {"data": copy.deepcopy(self.task_input)}
        if kind == "parameters" and config.get("dataset_fields"):
            return {"data": self.parameters["dataset"]}
        if kind == "parameters":
            return {"data": {"parameters": self.parameters}}
        if kind == "database":
            return {
                "data": read_database(
                    self.store, node_id, self.connection(config["connection"]), self.settings, config, self.parameters
                )
            }
        if kind in {"classification", "databaselookup"}:
            from langflow.business import classification, lookup

            executor = classification if kind == "classification" else lookup
            return executor.execute(self, node, incoming["data"][0])
        if kind == "api":
            if config.get("collection"):
                from langflow.business.collection import execute

                return execute(self, node, incoming["data"][0])
            return api_read(
                self.store,
                node_id,
                config,
                self.connection(config["connection"]),
                self.settings,
                self.parameters,
                incoming.get("data", [None])[0],
            )
        if kind == "file":
            return {"data": file_read(self.store, node_id, config, self.task.owner_id)}
        from langflow.business.catalog import PLUGINS

        if kind in PLUGINS:
            return PLUGINS[kind].execute(self, node, incoming)
        if kind == "model":
            return model_read(
                self.store, node_id, config, self.connection(config["connection"]), self.settings, incoming["data"][0]
            )
        parents = [r["id"] for refs in incoming.values() for r in refs]
        if kind == "join":
            left, right = incoming["left"][0], incoming["right"][0]
            queries = join_queries(
                config,
                self.store.relation(left["id"]),
                self.store.relation(right["id"]),
                fields_of(left),
                fields_of(right),
            )
        elif kind == "union":
            chunks = []
            for ref in incoming["data"]:
                excluded = ", ".join(
                    ident(f) for f in fields_of(ref) if f in {ROW_ID, "_source_row_id", "_source_dataset_id"}
                )
                chunks.append(
                    f"SELECT * EXCLUDE({excluded}), {ident(ROW_ID)} AS _source_row_id, "
                    f"{literal(ref['id'])} AS _source_dataset_id FROM {self.store.relation(ref['id'])}"
                )
            query = " UNION ALL BY NAME ".join(chunks)
            if config.get("deduplicate"):
                msg = "Move Union deduplication into Validate identity configuration"
                raise ValueError(msg)
            queries = {"data": f"SELECT *, row_number() OVER ()-1 AS {ident(ROW_ID)} FROM ({query})"}
        else:
            source = incoming["data"][0]
            if kind == "validate" and config.get("identity"):
                queries = identity_queries(
                    config, self.store.relation(source["id"]), fields_of(source), self.store.facts(source["id"])
                )
            else:
                queries = unary_query(
                    kind, config, self.store.relation(source["id"]), fields_of(source), self.parameters
                )
        if kind in {"aggregate", "compare", "model"}:
            incomplete = any(
                self.store.get(p).provenance.get("completeness", {}).get("state") != "complete" for p in parents
            )
            if incomplete:
                # Mark facts before computing comparisons; received rows are not proof of a complete range.
                reason = "source_range_unconfirmed"
                if kind == "compare":
                    blocked = (
                        f"SELECT *, {literal(reason)} AS _dependency_block FROM {self.store.relation(source['id'])}"
                    )
                    queries = unary_query(
                        kind, config, f"({blocked})", [*fields_of(source), "_dependency_block"], self.parameters
                    )
                else:
                    queries["data"] = (
                        f"SELECT * EXCLUDE(_blocking_reason), {literal(reason)} "
                        f"_blocking_reason FROM ({queries['data']})"
                    )
            if kind == "aggregate":
                blockers = self.store.get(source["id"]).provenance.get("blockers", [])
                for blocker in blockers:
                    available = {f["name"] for f in self.store.get(blocker).fields}
                    groups = config.get("group_by", [])
                    localized = [g for g in groups if g in available]
                    match = " AND ".join(
                        f"(b.{ident(g)} IS NULL OR b.{ident(g)} IS NOT DISTINCT FROM a.{ident(g)})" for g in localized
                    )
                    affected = (
                        (f"EXISTS (SELECT 1 FROM {self.store.relation(blocker)} b WHERE " + match + ")")
                        if localized
                        else "TRUE"
                    )
                    queries["data"] = (
                        f"SELECT * EXCLUDE(_blocking_reason), concat_ws(';', nullif(_blocking_reason,''), "
                        f"CASE WHEN {affected} THEN 'invalid_member' END) _blocking_reason FROM ({queries['data']}) a"
                    )
        outputs = {
            port: self.store.query(
                node_id,
                query,
                port=port,
                parents=parents,
                details={"operation": kind, "configuration": config},
                name=config.get("name") if kind == "output" else node.get("label"),
            )
            for port, query in queries.items()
        }
        # Problem rows carry their dependency scope even when downstream consumes only the valid port.
        inherited = list(
            dict.fromkeys(
                issue for parent in parents for issue in self.store.get(parent).provenance.get("blockers", [])
            )
        )
        if kind == "join":
            inherited = []
            for side, parent in [("left", left), ("right", right)]:
                for blocker in self.store.get(parent["id"]).provenance.get("blockers", []):
                    columns = ", ".join(
                        f"{ident(f['name'])} AS {ident(side + '_' + f['name'])}" for f in self.store.get(blocker).fields
                    )
                    mapped = self.store.query(
                        node_id, f"SELECT {columns} FROM {self.store.relation(blocker)}", port="blockers"
                    )
                    inherited.append(mapped["id"])
            # Join issues are a dependency too; use the known side fields to localize blocked groups.
            if outputs["issues"]["row_count"]:
                for side, parent in [("left", left), ("right", right)]:
                    columns = ", ".join(
                        f"{ident(f)} AS {ident(side + '_' + f)}" for f in fields_of(parent) if f != ROW_ID
                    )
                    mapped = self.store.query(
                        node_id,
                        f"SELECT {columns} FROM "
                        f"{self.store.relation(outputs['issues']['id'])} WHERE "
                        f"_issue_side={literal(side)}",
                        port="blockers",
                    )
                    if mapped["row_count"]:
                        inherited.append(mapped["id"])
        from langflow.business.models import Dataset

        if kind == "validate":
            # Issues also contains already-merged duplicate notices. Only actual
            # validation errors may block a dependent aggregate or comparison.
            errors = self.store.query(
                node_id,
                f"SELECT * FROM {self.store.relation(outputs['issues']['id'])} WHERE _issue_severity='error'",
                port="blockers",
                parents=[outputs["issues"]["id"]],
            )
            if errors["row_count"]:
                inherited.append(errors["id"])
            with self.database.sessions.begin() as session:
                issue_dataset = session.get(Dataset, outputs["issues"]["id"])
                issue_dataset.provenance = {**issue_dataset.provenance, "blocking_rows": errors["row_count"]}

        for port, ref in outputs.items():
            blockers = inherited if port != "issues" else []
            if blockers:
                with self.database.sessions.begin() as session:
                    row = session.get(Dataset, ref["id"])
                    row.provenance = {**row.provenance, "blockers": blockers}
        if kind == "aggregate":
            source = incoming["data"][0]
            groups = config.get("group_by", [])
            on = " AND ".join(f"s.{ident(g)} IS NOT DISTINCT FROM g.{ident(g)}" for g in groups) or "TRUE"
            query = (
                f"SELECT g.{ident(ROW_ID)} AS group_row_id, s.{ident(ROW_ID)} AS source_row_id "
                f"FROM {self.store.relation(source['id'])} s "
                f"JOIN {self.store.relation(outputs['data']['id'])} g ON {on}"
            )
            outputs["members"] = self.store.query(
                node_id, query, port="members", parents=[source["id"], outputs["data"]["id"]]
            )
        for port, ref in outputs.items():
            if port == "members":
                continue
            relation = self.store.relation(ref["id"])
            if kind == "aggregate":
                mapping = (
                    f"SELECT group_row_id row_id, {literal(source['id'])} parent_id, source_row_id parent_row_id "
                    f"FROM {self.store.relation(outputs['members']['id'])}"
                )
            elif kind == "join" and port == "data":
                mapping = " UNION ALL ".join(
                    f"SELECT {ident(ROW_ID)} row_id, {literal(parent['id'])} parent_id, "
                    f"{ident(side + '_' + ROW_ID)} parent_row_id FROM {relation}"
                    for side, parent in [("left", left), ("right", right)]
                )
            elif kind == "join":
                mapping = (
                    f"SELECT {ident(ROW_ID)} row_id, CASE WHEN _issue_side='left' THEN {literal(left['id'])} "
                    f"ELSE {literal(right['id'])} END parent_id, _join_source_row_id parent_row_id FROM {relation}"
                )
            elif kind == "union":
                mapping = (
                    f"SELECT {ident(ROW_ID)} row_id, _source_dataset_id parent_id, "
                    f"_source_row_id parent_row_id FROM {relation}"
                )
            elif kind == "validate" and config.get("identity") and port == "valid":
                mapping = (
                    f"SELECT _representative_row_id row_id, {literal(source['id'])} "
                    f"parent_id, {ident(ROW_ID)} parent_row_id "
                    f"FROM ({queries['valid']} UNION ALL SELECT * FROM ({queries['issues']}) "
                    "WHERE _issue_severity='info' AND _identity_status='exact_duplicate')"
                )
            else:
                mapping = (
                    f"SELECT {ident(ROW_ID)} row_id, {literal(source['id'])} parent_id, "
                    f"{ident(ROW_ID)} parent_row_id FROM {relation}"
                )
            self.store.link(ref, mapping, parents)
        if kind == "output":
            self.output_ids.append(outputs["data"]["id"])
        return outputs

    async def run_graph(self):
        from lfx.graph import Graph

        kinds = classes()
        components = {node["id"]: kinds[node["kind"]](_id=node["id"]) for node in self.graph["nodes"]}
        graph = Graph(flow_id=self.task.id, user_id=self.task.owner_id)
        for component in components.values():
            graph.add_component(component)
        for edge in self.graph["edges"]:
            graph.add_component_edge(edge["source"], (edge["port"], "input_" + edge["input"]), edge["target"])
        graph.initialize()
        token = ACTIVE_RUNTIME.set(self)
        try:
            async for result in graph.async_start():
                if hasattr(result, "valid") and result.valid is False:
                    msg = "Langflow graph node failed"
                    raise ValueError(msg)
            # Disconnected output branches also participate in the immutable job.
            if set(self.outputs) != set(self.nodes):
                msg = "Graph finished without executing every registered node"
                raise ValueError(msg)
            result_nodes = [n for n in self.graph["nodes"] if n["kind"] == "output"]
            result_nodes.sort(key=lambda n: not n["config"].get("primary", False))
            self.output_ids = [self.outputs[n["id"]]["data"]["id"] for n in result_nodes]
        finally:
            ACTIVE_RUNTIME.reset(token)


async def run_task(database, settings, task_id):
    from langflow.business.compiler import runtime_digest
    from langflow.business.models import Release
    from langflow.verification.database import fingerprint

    with database.sessions.begin() as session:
        task = session.get(Task, task_id, with_for_update=True)
        if task.started or task.status not in {"waiting", "running"}:
            msg = "Task has already started; a lost receipt must not duplicate external calls"
            raise ValueError(msg)
        release = session.get(Release, task.release_id)
        if (
            fingerprint(release.package) != release.content_hash
            or release.package["runtime_digest"] != runtime_digest()
        ):
            msg = "Published runtime differs; publish against this runtime before submitting new tasks"
            raise ValueError(msg)
        from sqlalchemy import update

        claimed = session.execute(
            update(Task)
            .where(Task.id == task_id, Task.started.is_(False), Task.status.in_(["waiting", "running"]))
            .values(started=True, status="running")
        )
        if claimed.rowcount != 1:
            msg = "Task was claimed by another execution"
            raise ValueError(msg)
    runtime = Runtime(database, settings, task, release.package)
    from langflow.business.coverage import finalize

    try:
        await runtime.run_graph()
        await asyncio.to_thread(finalize, runtime)
        with database.sessions.begin() as session:
            task = session.get(Task, task_id)
            task.status = "failed" if runtime.failures else "completed"
            if runtime.failures:
                task.error = {
                    "type": "NodeFailures",
                    "message": "Execution ended with failed nodes",
                    "nodes": runtime.failures,
                }
            task.results = runtime.output_ids
            task.finished_at = now()
    except BaseException as exc:
        try:
            await asyncio.to_thread(finalize, runtime)
        except Exception as assessment_error:  # noqa: BLE001 - Report failed finalization without inventing results.
            runtime.failures["assessment"] = type(assessment_error).__name__
        with database.sessions.begin() as session:
            task = session.get(Task, task_id)
            task.status = "needs_confirmation" if isinstance(exc, asyncio.CancelledError) else "failed"
            task.results = runtime.output_ids
            task.error = {"type": type(exc).__name__, "message": str(exc)[:2000], "nodes": runtime.failures}
            task.finished_at = now()
        raise
