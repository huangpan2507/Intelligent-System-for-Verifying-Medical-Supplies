# ruff: noqa: INP001, S101, F811, PLR2004 - standalone integration suite with shared fixtures.
"""Regulator intake through the actual Langflow graph, preserving task identity."""

from uuid import uuid4

import httpx
import pytest
from langflow.business.compiler import inspect_graph
from langflow.business.components import from_langflow, to_langflow
from langflow.business.datasets import DatasetStore
from langflow.business.models import Release, Scheme, Task, TaskInput, initialize
from langflow.business.runtime import run_task
from langflow.business.task_input import CONTRACT
from langflow.verification.api import create_app
from langflow.verification.database import fingerprint
from sqlalchemy import select
from test_workflows import OWNER, env, file_graph  # noqa: F401


def regulatory_graph(env):
    graph = file_graph(env)
    graph["nodes"].insert(0, {"id": "Request", "kind": "taskinput", "config": {}})
    graph["nodes"].insert(
        2,
        {
            "id": "Hospital",
            "kind": "filter",
            "config": {"conditions": [{"field": "code", "op": "eq", "parameter": "hospital_name"}]},
        },
    )
    graph["edges"] = [
        {"source": "Request", "target": "Source", "port": "data", "input": "data"},
        {"source": "Source", "target": "Hospital", "port": "data", "input": "data"},
        {"source": "Hospital", "target": "Result", "port": "matched", "input": "data"},
    ]
    return graph


@pytest.fixture
def released(env):
    db, settings = env
    graph = from_langflow(to_langflow(regulatory_graph(env)))
    package = inspect_graph(graph, db, settings, OWNER)
    with db.sessions.begin() as session:
        release = Release(scheme_code="regulatory.test", version=1, package=package, content_hash=fingerprint(package))
        session.add(release)
        session.flush()
        scheme = Scheme(
            code=release.scheme_code,
            name="Joint verification",
            owner_id=OWNER,
            flow_id=str(uuid4()),
            draft=graph,
            active_release_id=release.id,
            allowed_sources=["a"],
        )
        session.add(scheme)
    return scheme, release


def request(hospital="A", **overrides):
    return {
        "scheme": "regulatory.test",
        "external_task_id": "REG-001",
        "parameters": {"hospital_name": hospital, "start": "2025-08-01 00:00:00", "end": "2025-08-31 23:59:59"},
        **overrides,
    }


async def test_intake_runs_native_graph_with_task_isolation_and_frozen_rule(env, released):
    db, settings = env
    scheme, release = released
    assert release.package["task_input"] == CONTRACT
    assert all("default" not in p and "enum" not in p for p in release.package["parameters"])
    headers = {"Authorization": "Bearer " + "a" * 20, "Idempotency-Key": "first"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        response = await http.post("/api/v1/business/tasks", headers=headers, json=request())
        assert response.status_code == 202, response.text
        first = response.json()
        assert first["task_input"]["task"]["external_task_id"] == "REG-001"
        assert (await http.post("/api/v1/business/tasks", headers=headers, json=request())).json()["id"] == first["id"]
        assert (
            await http.post("/api/v1/business/tasks", headers=headers, json=request(external_task_id="other"))
        ).status_code == 409
        headers["Idempotency-Key"] = "second"
        response = await http.post(
            "/api/v1/business/tasks", headers=headers, json=request("B", external_task_id="REG-002")
        )
        assert response.status_code == 202
        second = response.json()
        # Accepted tasks retain the old version and rule label after the scheme changes.
        with db.sessions.begin() as session:
            row = session.get(Scheme, scheme.code)
            row.name = "Renamed later"
            row.active_release_id = None
        for entry, hospital in [(first, "A"), (second, "B")]:
            await run_task(db, settings, entry["id"])
            with db.sessions() as session:
                task = session.get(Task, entry["id"])
                assert task.status == "completed", task.error
                actual = task.progress["Request"]["outputs"]["data"]
                assert actual == entry["task_input"]
                assert actual["task"]["rule_name"] == "Joint verification"
                assert actual["task"]["release_id"] == release.id
                assert actual["parameters"]["hospital_name"] == hospital
                rows = DatasetStore(db, task.id).page(task.results[0])["rows"]
                assert [r["code"] for r in rows] == [hospital]
            detail = await http.get(f"/api/v1/business/tasks/{entry['id']}", headers=headers)
            assert detail.json()["task_input"] == entry["task_input"]
            hidden = await http.get(
                f"/api/v1/business/tasks/{entry['id']}", headers={"Authorization": "Bearer " + "b" * 20}
            )
            assert hidden.status_code == 404
        admin = {"Authorization": "Bearer " + "i" * 20, "X-Business-Actor": OWNER}
        listed = await http.get(f"/api/v1/business/internal/tasks?flow_id={scheme.flow_id}", headers=admin)
        assert listed.json()["total"] == 2
        assert (await http.get(f"/api/v1/business/internal/tasks?flow_id={uuid4()}", headers=admin)).json()[
            "total"
        ] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"external_task_id": None},
        {"external_task_id": "   "},
        {"parameters": {}},
        {"hospital_name": ""},
        {"hospital_name": 12},
        {"start": "2025-08-01"},
        {"start": "2025-02-30 00:00:00"},
        {"start": "2025-09-01 00:00:00"},
        {"end": "invalid"},
        {"extra": "unexpected"},
    ],
)
@pytest.mark.usefixtures("released")
async def test_bad_intake_does_not_create_task_or_fill_defaults(env, change):
    db, settings = env
    body = request()
    if "external_task_id" in change or "parameters" in change:
        body.update(change)
    else:
        body["parameters"].update(change)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, db)), base_url="http://test"
    ) as http:
        response = await http.post(
            "/api/v1/business/tasks",
            json=body,
            headers={"Authorization": "Bearer " + "a" * 20, "Idempotency-Key": "bad"},
        )
        assert response.status_code == 422, response.text
    with db.sessions() as session:
        assert session.scalar(select(Task)) is None
        assert session.scalar(select(TaskInput)) is None


def test_task_contract_cannot_be_edited_or_duplicated(env):
    db, settings = env
    graph = regulatory_graph(env)
    graph["nodes"][0]["config"] = {"parameters": [{"name": "hospital_name", "default": "wrong"}]}
    assert "Request" in inspect_graph(graph, db, settings, OWNER, strict=False)["errors"]
    graph["nodes"][0]["config"] = {}
    graph["nodes"].append({"id": "Other", "kind": "parameters", "config": {}})
    assert "task_input" in inspect_graph(graph, db, settings, OWNER, strict=False)["errors"]


def test_additive_input_storage_preserves_existing_tasks(env):
    db, _ = env
    TaskInput.__table__.drop(db.engine)
    with db.sessions.begin() as session:
        session.add(
            Task(
                id="old",
                owner_id=OWNER,
                source="a",
                idempotency_key="old",
                content_hash="old",
                scheme_code="old",
                release_id="old",
                parameters={"legacy": 1},
            )
        )
    initialize(db)
    initialize(db)
    with db.sessions() as session:
        assert session.get(Task, "old").parameters == {"legacy": 1}
        assert session.scalar(select(TaskInput)) is None
