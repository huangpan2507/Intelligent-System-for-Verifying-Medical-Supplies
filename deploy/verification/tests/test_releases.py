import copy
from uuid import uuid4

import pytest
from conftest import ACTOR, INTERNAL_TOKEN, draft_graph
from langflow.verification.database import Database
from langflow.verification.demo import example_task
from langflow.verification.releases import compile_release, require_runtime
from sqlalchemy import create_engine, text

HEADERS = {"Authorization": f"Bearer {INTERNAL_TOKEN}", "X-Verification-Actor": ACTOR}
PATH = "/api/v1/verification/internal/rules/high_value_consumables"


async def test_candidate_simulation_publish_activate_are_separate(client):
    graph = draft_graph()
    response = await client.post(
        PATH + "/candidates",
        headers=HEADERS,
        json={
            "graph": graph,
            "catalog_mapping": {"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"},
            "note": "candidate check",
        },
    )
    assert response.status_code == 201, response.text
    candidate = response.json()
    assert candidate["validation"]["simulation"] == "passed"
    assert candidate["validation"]["summary"]["details"] == 3
    before = (await client.get("/api/v1/verification/internal/rules", headers=HEADERS)).json()[0]
    body = {"candidate_id": candidate["id"], "content_hash": candidate["content_hash"]}
    release = await client.post(PATH + "/releases", headers=HEADERS, json=body)
    assert release.status_code == 201, release.text
    assert (await client.post(PATH + "/releases", headers=HEADERS, json=body)).json()["id"] == release.json()["id"]
    still = (await client.get("/api/v1/verification/internal/rules", headers=HEADERS)).json()[0]
    assert still["active_release_id"] == before["active_release_id"]
    activate = {"release_id": release.json()["id"], "expected_revision": before["revision"]}
    assert (await client.put(PATH + "/active", headers=HEADERS, json=activate)).status_code == 200
    assert (await client.put(PATH + "/active", headers=HEADERS, json=activate)).status_code == 409
    body["content_hash"] = "0" * 64
    assert (await client.post(PATH + "/releases", headers=HEADERS, json=body)).status_code == 409
    other = {**HEADERS, "X-Verification-Actor": str(uuid4())}
    assert (await client.get(PATH + "/releases", headers=other)).status_code == 404


@pytest.mark.parametrize("mutation", ["missing_stage", "frozen", "global", "edited_code", "edge", "duplicate"])
def test_unsafe_or_incomplete_drafts_fail_release_check(settings, mutation):
    graph = draft_graph()
    if mutation == "missing_stage":
        graph["nodes"].pop()
    if mutation == "duplicate":
        graph["nodes"][-1] = copy.deepcopy(graph["nodes"][-2])
    node = graph["nodes"][3]["data"]["node"]
    if mutation == "frozen":
        node["frozen"] = True
    if mutation == "global":
        node["template"]["filter_match"]["load_from_db"] = True
    if mutation == "edited_code":
        node["template"]["code"]["value"] += "\n# unreviewed change"
    if mutation == "edge":
        graph["edges"][2]["target"] = graph["edges"][2]["source"]
    with pytest.raises((ValueError, KeyError)):
        compile_release(graph, {"DEMO-HIP": "hip_prosthesis"}, settings, flow_id=str(uuid4()), owner_id=ACTOR)


def test_missing_runtime_cannot_silently_use_new_code(settings):
    package = compile_release(
        draft_graph(), {"DEMO-HIP": "hip_prosthesis"}, settings, flow_id=str(uuid4()), owner_id=ACTOR
    )
    package["runtime_digest"] = "0" * 64
    with pytest.raises(ValueError, match="运行构建"):
        require_runtime(package)


def test_old_trial_schema_is_never_silently_upgraded(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("create table task (id text)"))
    database = Database(url)
    with pytest.raises(RuntimeError, match="Trial schema"):
        database.initialize()
    database.engine.dispose()
    engine.dispose()


@pytest.mark.parametrize(
    ("mutation", "status"),
    [("unknown_hospital", 422), ("unknown_rule", 422), ("bad_time", 422), ("old_contract", 422), ("unauthorized", 403)],
)
async def test_scope_contract_errors(client, mutation, status):
    body = example_task()
    headers = {"Idempotency-Key": str(uuid4())}
    if mutation == "unknown_hospital":
        body["hospital_scope"] = "unregistered hospital"
    if mutation == "unknown_rule":
        body["rule"] = "no rule"
    if mutation == "old_contract":
        body["detail_ids"] = ["detail-hip"]
    if mutation == "bad_time":
        body["settlement_time_range"]["end_exclusive"] = body["settlement_time_range"]["start_inclusive"]
    if mutation == "unauthorized":
        headers["Authorization"] = "Bearer other-client-token-123456"
    assert (await client.post("/api/v1/verification/tasks", json=body, headers=headers)).status_code == status


async def test_rule_draft_persists_without_activating_and_rejects_lost_updates(client):
    before = (await client.get("/api/v1/verification/internal/rules", headers=HEADERS)).json()[0]
    body = {"catalog_mapping": {"CUSTOM": "hip_prosthesis"}, "note": "draft only", "expected_revision": 0}
    saved = await client.put(PATH + "/draft", headers=HEADERS, json=body)
    assert saved.status_code == 200, saved.text
    current = (await client.get("/api/v1/verification/internal/rules", headers=HEADERS)).json()[0]
    assert current["draft_config"]["catalog_mapping"] == body["catalog_mapping"]
    assert current["draft_revision"] == 1
    assert current["active_release_id"] == before["active_release_id"]
    assert (await client.put(PATH + "/draft", headers=HEADERS, json=body)).status_code == 409


async def test_candidate_graph_accepts_selected_comparison_kinds(client):
    graph = draft_graph()
    node = next(n for n in graph["nodes"] if n["id"].endswith("-07"))
    node["data"]["node"]["template"]["comparisons"]["value"] = ["种类"]
    response = await client.post(
        PATH + "/candidates",
        headers=HEADERS,
        json={"graph": graph, "catalog_mapping": {"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"}},
    )
    assert response.status_code == 201, response.text
    assert response.json()["validation"]["summary"]["consistent"] == 2
