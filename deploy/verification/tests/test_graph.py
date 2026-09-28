# ruff: noqa: RUF001 - Match the component's Chinese UI labels exactly.
import asyncio
import importlib.util
import json
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request
from langflow.verification.demo import create_demo_app, example_task
from lfx.graph import Graph
from lfx.schema.schema import InputValueRequest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("filename", ["consumable-verification.json", "consumable-verification-palette.json"])
def test_exported_flow_has_canvas_nodes_and_connected_handles(filename):
    payload = json.loads((ROOT / "deploy/verification" / filename).read_text())
    nodes = {node["id"]: node for node in payload["data"]["nodes"]}
    assert len(nodes) == 10
    assert len(payload["data"]["edges"]) == 9
    for node in nodes.values():
        assert node.get("type") == "genericNode"
        if node["id"].endswith("-05"):
            assert node["data"]["node"]["template"]["series_url"]["show"] is True
            assert node["data"]["node"]["template"]["images_url"]["show"] is True
        elif node["id"].endswith("-06"):
            assert node["data"]["node"]["template"]["model_api_url"]["show"] is True
    for edge in payload["data"]["edges"]:
        assert edge["id"]
        for name in ("sourceHandle", "targetHandle"):
            assert json.loads(edge[name].replace("œ", '"')) == edge["data"][name]
        assert edge["data"]["sourceHandle"]["dataType"] == nodes[edge["source"]]["data"]["type"]
        assert nodes[edge["source"]]["position"]["x"] < nodes[edge["target"]]["position"]["x"]


@contextmanager
def live_service(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


@pytest.mark.graph
@pytest.mark.parametrize("palette", [False, True], ids=["legacy", "palette"])
@pytest.mark.parametrize("scenario", ["default", "filter", "comparison", "window", "modality", "body", "api_urls"])
async def test_actual_langflow_graph_over_http(client, settings, database, app, monkeypatch, scenario, palette):
    response = await client.post("/api/v1/verification/tasks", json=example_task("actual-graph"))
    accepted = response.json()
    assert response.status_code == 202
    assert database.claim() == accepted["run_id"]
    spec = importlib.util.spec_from_file_location(
        "verification_flow_builder", ROOT / "scripts/verification/build_flow.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    upstream = FastAPI()
    requests = []
    cloud_requests = []

    @upstream.middleware("http")
    async def record_request(request: Request, call_next):
        requests.append((request.method, request.url.path))
        if "/api/v2/" in request.url.path:
            cloud_requests.append((request.url.path, dict(request.query_params)))
            assert request.headers.get("x-token") == settings.upstream_token.get_secret_value()
            assert "authorization" not in request.headers
        return await call_next(request)

    upstream.mount("/configured", create_demo_app(settings))
    upstream.mount("/", create_demo_app(settings))
    with live_service(app) as business_url, live_service(upstream) as upstream_url:
        monkeypatch.setenv("VERIFICATION_API_URL", business_url)
        monkeypatch.setenv("VERIFICATION_INTERNAL_TOKEN", settings.internal_token.get_secret_value())
        monkeypatch.setenv("VERIFICATION_UPSTREAM_TOKEN", settings.upstream_token.get_secret_value())
        monkeypatch.setenv("VERIFICATION_SETTLEMENT_URL", upstream_url)
        monkeypatch.setenv("VERIFICATION_IMAGING_URL", upstream_url)
        monkeypatch.setenv("VERIFICATION_MODEL_URL", upstream_url)
        monkeypatch.setenv("VERIFICATION_DEMO_MODE", "true")
        # Round-trip through the import format, so embedded component code is exercised too.
        payload = (
            json.loads(await asyncio.to_thread(Path(os.environ["VERIFICATION_TEST_BROWSER_FLOW"]).read_text))["data"]
            if palette == "browser"
            else module.build_payload(palette=palette)["data"]
        )
        expected_ids = [node["id"] for node in payload["nodes"]]
        nodes = {node["id"][-2:]: node["data"]["node"]["template"] for node in payload["nodes"]}
        if scenario == "filter":
            nodes["02"]["filter_conditions"]["value"] = [
                {"field": "数量（quantity）", "operator": "大于等于", "value": "2"}
            ]
        elif scenario == "comparison":
            nodes["07"]["comparisons"]["value"] = ["数量"]
            nodes["07"]["quantity_tolerance"]["value"] = 1
        elif scenario == "window":
            nodes["03"]["days_before"]["value"] = 0
            nodes["03"]["days_after"]["value"] = 0
        elif scenario == "modality":
            nodes["03"]["modalities"]["value"] = ["CT"]
        elif scenario == "body":
            nodes["04"]["body_field"]["value"] = "项目名称（project_name）"
            nodes["04"]["body_rules"]["value"] = [{"category": "明确无关", "term": "Synthetic hip radiograph"}]
        elif scenario == "api_urls":
            nodes["03"]["studies_url"]["value"] = f"{upstream_url}/configured/api/v2/study/list"
            nodes["05"]["series_url"]["value"] = (
                f"{upstream_url}/configured/api/v2/dicom/series-instance-uid?study_primary_id={{study_primary_id}}"
            )
            nodes["05"]["images_url"]["value"] = (
                f"{upstream_url}/configured/api/v2/storage/dicom/sop-instance-uid?series_id={{series_id}}&url_type=4"
            )
            nodes["06"]["model_api_url"]["value"] = f"{upstream_url}/configured/v1/recognitions"
        graph = Graph.from_payload(payload)
        entry = {key: accepted[key] for key in ("task_id", "run_id", "detail_ids")}
        if palette:
            # The run API uses arun with the Worker's explicit input_type=any for custom input nodes.
            await graph.arun(inputs=[{"input_value": json.dumps(entry)}], types=["any"])
            assert all(graph.get_vertex(node_id).built for node_id in expected_ids)
        else:
            outputs = [
                step async for step in graph.async_start(inputs=InputValueRequest(input_value=json.dumps(entry)))
            ]
            executed = [step.vertex.id for step in outputs if hasattr(step, "vertex")]
            assert executed == expected_ids
    result = (await client.get(f"/api/v1/verification/tasks/{accepted['task_id']}/results")).json()
    assert result["status"] == "completed"
    hip, knee = result["result"]["results"]
    evidence = (await client.get(f"/api/v1/verification/tasks/{accepted['task_id']}/evidence")).json()
    if scenario in {"default", "api_urls"}:
        assert hip["fee"]["delta"] == "-10000.00"
        assert knee["conclusion"] == "consistent"
        assert len(evidence["model_requests"]) == 2
        configuration = hip["node_configurations"]
        prefix = f"{upstream_url}/configured" if scenario == "api_urls" else upstream_url
        assert configuration["03"]["studies_url"] == f"{prefix}/api/v2/study/list"
        assert configuration["05"]["series_url"] == (
            f"{prefix}/api/v2/dicom/series-instance-uid?study_primary_id={{study_primary_id}}"
        )
        assert configuration["05"]["images_url"] == (
            f"{prefix}/api/v2/storage/dicom/sop-instance-uid?series_id={{series_id}}"
            + ("&url_type=4" if scenario == "api_urls" else "")
        )
        assert configuration["06"]["model_api_url"] == f"{prefix}/v1/recognitions"
        manifest = next(a["payload"] for a in evidence["artifacts"] if a["kind"] == "manifest")
        assert manifest["configuration"] == configuration["05"]
        endpoint_requests = [
            (method, path)
            for method, path in requests
            if path.endswith(("/series-instance-uid", "/sop-instance-uid", "/recognitions"))
        ]
        route_prefix = "/configured" if scenario == "api_urls" else ""
        assert sorted(endpoint_requests) == sorted(
            [("POST", f"{route_prefix}/v1/recognitions")] * 2
            + [("GET", f"{route_prefix}/api/v2/dicom/series-instance-uid")] * 2
            + [("GET", f"{route_prefix}/api/v2/storage/dicom/sop-instance-uid")] * 2
        )
        study_queries = [q for path, q in cloud_requests if path.endswith("/study/list")]
        assert len(study_queries) == 4
        assert {q["system_patient_id"] for q in study_queries} == {"synthetic-patient-hip", "synthetic-patient-knee"}
        assert all(q["organ_code"] == "synthetic-hospital" and q["op_em_hp_ex_mark"] == "3" for q in study_queries)
        series_queries = [q for path, q in cloud_requests if path.endswith("/series-instance-uid")]
        assert {q["study_primary_id"] for q in series_queries} == {"study-hip", "study-knee"}
        image_queries = [q for path, q in cloud_requests if path.endswith("/sop-instance-uid")]
        assert {q["series_id"] for q in image_queries} == {"series-hip", "series-knee"}
        if scenario == "api_urls":
            assert all(q["url_type"] == "4" for q in image_queries)
        assert all(group["series"] for group in manifest["groups"])
        assert manifest["groups"][0]["images"][0]["url"].endswith(".dcm?synthetic=1")
    elif scenario == "filter":
        assert hip["conclusion"] == "difference"
        assert knee["conclusion"] == "not_compared"
        assert "configured_filter_not_matched" in knee["quantity"]["reasons"]
        assert len(evidence["model_requests"]) == 1
        selection = next(a["payload"] for a in evidence["artifacts"] if a["kind"] == "selection")
        assert selection["configuration"]["conditions"][0]["value"] == "2"
        assert hip["node_configurations"]["02"] == selection["configuration"]
    elif scenario == "comparison":
        assert hip["conclusion"] == "consistent"
        assert hip["quantity"]["delta"] == "-1"
        assert Decimal(hip["quantity"]["tolerance"]) == 1
        assert hip["fee"]["status"] == "not_requested"
        assert hip["comparison_rules"]["comparisons"] == ["quantity"]
    elif scenario in {"window", "modality"}:
        assert not evidence["model_requests"]
        assert hip["conclusion"] == knee["conclusion"] == "not_compared"
    elif scenario == "body":
        assert hip["conclusion"] == "not_compared"
        assert knee["conclusion"] == "consistent"
        assert len(evidence["model_requests"]) == 1


@pytest.mark.graph
async def test_browser_assembled_flow_over_http(client, settings, database, app, monkeypatch):
    if not os.getenv("VERIFICATION_TEST_BROWSER_FLOW"):
        pytest.skip("Set VERIFICATION_TEST_BROWSER_FLOW to a flow actually dragged and connected in the browser")
    await test_actual_langflow_graph_over_http(client, settings, database, app, monkeypatch, "default", "browser")
