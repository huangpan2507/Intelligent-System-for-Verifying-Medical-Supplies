import json
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from langflow.verification.demo import create_demo_app
from lfx.graph import Graph

ROOT = Path(__file__).resolve().parents[3]


def test_exported_flow_has_canvas_nodes_and_connected_handles():
    payload = json.loads((ROOT / "deploy/verification/consumable-verification-palette.json").read_text())
    nodes = {node["id"]: node for node in payload["data"]["nodes"]}
    assert len(nodes) == 10
    assert len({node["data"]["type"] for node in nodes.values()}) == 10
    assert len(payload["data"]["edges"]) == 9
    for node in nodes.values():
        assert node.get("type") == "genericNode"
        assert node["data"]["type"].startswith("ext:verification:Verification")
        assert not node["data"]["node"].get("legacy")
        assert "stage" not in node["data"]["node"]["template"]
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
async def test_actual_published_graph_over_http(client, settings, database, app, monkeypatch):
    import httpx
    from conftest import seed_release
    from langflow.verification.pipeline import Pipeline
    from test_api_pipeline import submit

    with live_service(app) as business_url, live_service(create_demo_app(settings)) as upstream_url:
        runtime = settings.model_copy(
            update={
                "api_url": business_url,
                "settlement_url": upstream_url,
                "imaging_url": upstream_url,
                "model_url": upstream_url,
            }
        )
        for key in ["api_url", "settlement_url", "imaging_url", "model_url"]:
            monkeypatch.setenv("VERIFICATION_" + key.upper(), getattr(runtime, key))
        monkeypatch.setenv("VERIFICATION_INTERNAL_TOKEN", settings.internal_token.get_secret_value())
        monkeypatch.setenv("VERIFICATION_UPSTREAM_TOKEN", settings.upstream_token.get_secret_value())
        monkeypatch.setenv("VERIFICATION_DEMO_MODE", "true")
        release = seed_release(database, runtime)
        accepted = await submit(client)
        assert database.claim() == accepted["run_id"]
        async with httpx.AsyncClient() as http:
            await Pipeline(runtime, http).internal("POST", accepted["run_id"], "/execution/start")
        graph = Graph.from_payload(release.package["graph"], flow_id=accepted["job_id"])
        payload = {key: accepted[key] for key in ["task_id", "run_id", "release_id", "job_id"]}
        result = await graph.arun(
            inputs=[{"input_value": json.dumps(payload)}], types=["any"], session_id=accepted["run_id"]
        )
        view = (await client.get(f"/api/v1/verification/tasks/{accepted['task_id']}/results")).json()
        assert view["available"] and view["status"] == "completed", result
        assert view["result"]["summary"]["details"] == 3
        assert view["result"]["summary"]["units"] == 2
