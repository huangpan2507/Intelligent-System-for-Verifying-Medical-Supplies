# ruff: noqa: S101, PLR2004, INP001, F811, S608 - result contract fixtures and quoted dataset relations.
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pyarrow as pa
import pytest
from langflow.business.catalog import CATALOG
from langflow.business.compiler import inspect_graph
from langflow.business.datasets import ROW_ID, DatasetStore, ident, literal
from langflow.business.models import BusinessResult, ExternalRequest, ResultEvidence, Task
from langflow.business.result_templates import prepare_output, render, template
from langflow.business.results import persist
from langflow.verification.api import create_app
from sqlalchemy import func, select
from test_workflows import (
    OWNER,
    env,  # noqa: F401 - shared pytest fixture
    file_graph,
    save_release,
)


@pytest.mark.parametrize(
    ("changes", "state", "expected", "absent"),
    [
        ({}, "normal", "三项比较一致", "尚未完成"),
        ({"category_status": "different"}, "difference", "存在类别差异", "存在数量"),
        (
            {
                "CNT": "2",
                "settled_amount": "20000",
                "quantity_status": "different",
                "amount_status": "different",
                "difference_1": "-1",
                "difference_2": "-10000",
            },
            "difference",
            "数量、折算金额差异",
            "三项比较一致",
        ),
        ({"quantity_status": "unknown", "recognized_quantity": None}, "incomplete", "数量尚未完成", "数量为0"),
        (
            {"category_status": "different", "amount_status": "unknown"},
            "difference",
            "折算金额尚未完成",
            "三项比较一致",
        ),
    ],
)
def test_narrative(changes, state, expected, absent):
    profile = template("hip_knee_v1")
    value = render(profile, {**profile["example"], **changes})
    assert value["status"] == state
    assert expected in value["narrative"]
    assert absent not in value["narrative"]
    assert value["complete"] == (not any(v == "unknown" for v in changes.values()))


def test_output_contract_and_missing_binding(env):
    assert not {"key_fields", "reason_fields", "evidence_fields"} & CATALOG["output"]["schema"]["properties"].keys()
    config = {"result_template": "hip_knee_v1", "columns": ["wrong"], "obligation": {"mode": "ordinary"}}
    profile = prepare_output(config, single=True)
    assert config["primary"]
    assert config["obligation"]["mode"] == "verification"
    assert {"image_manifest_context", "_request_id", "_identity"} <= set(config["columns"])
    graph = file_graph(env)
    next(n for n in graph["nodes"] if n["kind"] == "output")["config"]["result_template"] = "hip_knee_v1"
    package = inspect_graph(graph, *env, OWNER, strict=False)
    assert package["errors"]
    assert package["result_templates"]
    assert profile["version"] == 1


@pytest.fixture
def runtime(env):
    db, settings = env
    release = save_release(env, file_graph(env))
    with db.sessions.begin() as session:
        task = Task(
            owner_id=OWNER,
            source="a",
            idempotency_key="result-test",
            content_hash="test",
            scheme_code=release.scheme_code,
            release_id=release.id,
            parameters={},
        )
        session.add(task)
        session.flush()
    store = DatasetStore(db, task.id)
    profile = template("hip_knee_v1")
    facts = {**profile["example"], "_identity": "identity-1"}
    unit_facts = {
        key: value
        for key, value in facts.items()
        if not key.startswith("recognized_") and not key.endswith("_status") and key != "observed_amount"
    }
    unit = store.write_batches("Classification", [[unit_facts]], pa.Table.from_pylist([unit_facts]).schema)
    unit_id = store.page(unit["id"])["rows"][0][ROW_ID]
    with db.sessions.begin() as session:
        request = ExternalRequest(
            task_id=task.id,
            node_id="Observation",
            input_dataset_id=unit["id"],
            input_row_id=unit_id,
            connection_id=str(uuid4()),
            payload={},
            response={"quantity": 1},
        )
        session.add(request)
        session.flush()
    row = {
        **facts,
        "unit_row_id": unit_id,
        "_request_id": request.id,
        "evidence_ref": "service-ref",
        "image_manifest_context": json.dumps(
            [
                {
                    "RPT_NO": "EXAMPLE-RPT",
                    "study_ris_study_id": "study-1",
                    "series_id": "series-1",
                    "address": "https://example.invalid/image",
                }
            ]
        ),
    }
    result = store.write_batches("Results", [[row]], pa.Table.from_pylist([row]).schema)
    store.link(
        result,
        f"SELECT {ident(ROW_ID)} row_id, {literal(unit['id'])} parent_id, unit_row_id parent_row_id "
        f"FROM {store.relation(result['id'])}",
        [unit["id"]],
    )
    return SimpleNamespace(
        database=db,
        store=store,
        task=task,
        package={"result_templates": {"Results": profile}},
        outputs={"Classification": {"data": unit}, "Results": {"data": result}},
        settings=settings,
    )


def test_atomic_idempotent_results_with_evidence(runtime):
    persist(runtime)
    runtime.package["result_templates"]["Results"]["version"] = 2
    persist(runtime)
    with runtime.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessResult)) == 1
        result = session.scalar(select(BusinessResult))
        assert result.status == "normal"
        assert result.facts["_request_id"]
        evidence = list(session.scalars(select(ResultEvidence)))
        assert {e.kind for e in evidence} == {"source", "recognition", "image"}
        assert next(e for e in evidence if e.kind == "image").context["RPT_NO"] == "EXAMPLE-RPT"
        assert result.template_version == 1


def test_incomplete_unit_is_saved_without_inventing_observations(runtime):
    runtime.outputs.pop("Results")
    persist(runtime)
    with runtime.database.sessions() as session:
        result = session.scalar(select(BusinessResult))
        assert result.status == "incomplete"
        assert not result.complete
        assert result.result_dataset_id is None
        assert result.facts["recognized_quantity"] is None
        assert "尚未完成" in result.narrative


def test_evidence_failure_rolls_back_result(runtime):
    row = runtime.store.page(runtime.outputs["Results"]["data"]["id"])["rows"][0]
    row["_request_id"] = str(uuid4())
    row.pop(ROW_ID)
    ref = runtime.store.write_batches("Broken", [[row]], pa.Table.from_pylist([row]).schema)
    runtime.outputs["Results"]["data"] = ref
    with pytest.raises(ValueError, match="does not belong"):
        persist(runtime)
    with runtime.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessResult)) == 0


async def test_saved_results_and_evidence_are_source_isolated(runtime):
    persist(runtime)
    with runtime.database.sessions() as session:
        result = session.scalar(select(BusinessResult))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime.settings, runtime.database)), base_url="http://fixture"
    ) as http:
        for suffix in ["results", f"results/{result.id}/evidence"]:
            url = f"/api/v1/business/tasks/{runtime.task.id}/{suffix}"
            response = await http.get(url, headers={"Authorization": "Bearer " + "a" * 20})
            assert response.status_code == 200
            assert response.json()["total"] > 0
            assert (await http.get(url, headers={"Authorization": "Bearer " + "b" * 20})).status_code == 404
        assert (
            await http.get(
                f"/api/v1/business/tasks/{runtime.task.id}/results/{uuid4()}/evidence",
                headers={"Authorization": "Bearer " + "a" * 20},
            )
        ).status_code == 404
