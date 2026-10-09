# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Run the exact release candidate against isolated synthetic services before publishing."""

import copy
import json
import tempfile
from contextvars import ContextVar
from pathlib import Path

import httpx

# Context-local injection affects only candidate validation, never another user's running graph.
# No deployment URL, environment variable or global HTTP client is mutated.
component_runtime: ContextVar[tuple | None] = ContextVar("verification_candidate_runtime", default=None)


async def validate_candidate(package: dict, settings) -> dict:
    from lfx.graph import Graph

    from langflow.verification.api import create_app
    from langflow.verification.database import (
        Database,
        ExecutionBinding,
        ReleaseCandidate,
        RuleDefinition,
        RuleRelease,
        fingerprint,
    )
    from langflow.verification.demo import create_demo_app, example_task, seed_demo

    if not package["simulated"]:
        msg = "当前仅交付模拟发布验证；真实接口和事实依据验收后才能开放正式发布"
        raise ValueError(msg)
    with tempfile.TemporaryDirectory(prefix="verification-candidate-") as directory:
        local = settings.model_copy(update={"database_url": f"sqlite:///{Path(directory) / 'candidate.db'}"})
        database = Database(local.database_url)
        database.initialize()
        seed_demo(database)
        with database.sessions.begin() as session:
            rule = RuleDefinition(
                code="high_value_consumables",
                name="高值耗材智能体",
                flow_id=package["flow_id"],
                owner_id=package["owner_id"],
            )
            session.add(rule)
            session.flush()
            candidate = ReleaseCandidate(
                rule_code=rule.code,
                content_hash=fingerprint(package),
                package=package,
                author_id=package["owner_id"],
                validation={},
                note="isolated validation",
            )
            session.add(candidate)
            session.flush()
            release = RuleRelease(
                rule_code=rule.code,
                version=1,
                candidate_id=candidate.id,
                content_hash=candidate.content_hash,
                package=package,
                author_id=package["owner_id"],
                note="isolated validation",
            )
            session.add(release)
            session.flush()
            binding = ExecutionBinding(release_id=release.id, config={**package["connections"], "simulated": True})
            session.add(binding)
            session.flush()
            rule.active_binding_id = binding.id
        business = httpx.ASGITransport(app=create_app(settings, database))
        upstream = httpx.ASGITransport(app=create_demo_app(settings))

        class SyntheticTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                target = business if request.url.path.startswith("/api/v1/verification/") else upstream
                return await target.handle_async_request(request)

        transport = SyntheticTransport()
        token = component_runtime.set((settings, transport))
        try:
            source_token = settings.clients.get("demo-regulator")
            if source_token is None:
                msg = "模拟发布验证需要配置demo-regulator来源"
                raise ValueError(msg)
            async with httpx.AsyncClient(transport=transport, base_url="http://candidate") as http:
                headers = {
                    "Authorization": f"Bearer {source_token.get_secret_value()}",
                    "Idempotency-Key": "validation",
                }
                response = await http.post("/api/v1/verification/tasks", headers=headers, json=example_task())
                response.raise_for_status()
                accepted = response.json()
                database.claim()
                internal = {"Authorization": f"Bearer {settings.internal_token.get_secret_value()}"}
                started = await http.post(
                    f"/api/v1/verification/internal/runs/{accepted['run_id']}/execution/start", headers=internal
                )
                started.raise_for_status()
                graph = Graph.from_payload(copy.deepcopy(package["graph"]), flow_id=accepted["job_id"])
                entry = {key: accepted[key] for key in ["task_id", "run_id", "release_id", "job_id"]}
                await graph.arun(
                    inputs=[{"input_value": json.dumps(entry)}], types=["any"], session_id=accepted["run_id"]
                )
                result = await http.get(f"/api/v1/verification/tasks/{accepted['task_id']}/results", headers=headers)
                result.raise_for_status()
                saved = result.json()
                if not saved["available"] or saved["status"] not in {"completed", "partial_failed"}:
                    msg = "候选流程未通过08业务保存验证"
                    raise ValueError(msg)
                return {
                    "structure": "passed",
                    "parameters": "passed",
                    "dependencies": "pinned",
                    "simulation": "passed",
                    "summary": saved["result"]["summary"],
                    "model_accuracy": "not_validated",
                }
        finally:
            component_runtime.reset(token)
            database.engine.dispose()
