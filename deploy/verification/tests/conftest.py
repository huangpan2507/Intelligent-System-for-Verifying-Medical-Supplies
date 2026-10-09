from uuid import uuid4

import httpx
import pytest
from langflow.verification.api import create_app
from langflow.verification.database import Database, ReleaseCandidate, RuleDefinition
from langflow.verification.demo import create_demo_app, seed_demo
from langflow.verification.releases import activate, compile_release, publish
from langflow.verification.schemas import ActivateRelease, PublishRelease
from langflow.verification.settings import VerificationSettings

CLIENT_TOKEN = "test-client-token-123456"
INTERNAL_TOKEN = "test-internal-token-123456"


@pytest.fixture(autouse=True)
def local_platform_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGFLOW_CONFIG_DIR", str(tmp_path / "langflow"))


@pytest.fixture
def settings(tmp_path):
    return VerificationSettings(
        database_url=f"sqlite:///{tmp_path}/verification.db",
        clients={"demo-regulator": CLIENT_TOKEN, "other-regulator": "other-client-token-123456"},
        internal_token=INTERNAL_TOKEN,
        upstream_token="test-upstream-token-123456",
        langflow_api_key="test-langflow-token-123456",
        api_url="http://business",
        settlement_url="http://upstream",
        imaging_url="http://upstream",
        model_url="http://upstream",
        langflow_url="http://flow",
        demo_mode=True,
    )


@pytest.fixture
def database(settings):
    db = Database(settings.database_url.get_secret_value())
    db.initialize()
    seed_release(db, settings)
    yield db
    db.engine.dispose()


@pytest.fixture
def app(settings, database):
    return create_app(settings, database)


class ServiceTransport(httpx.AsyncBaseTransport):
    """Route real HTTP requests to in-process ASGI services; optionally inject an external fault."""

    def __init__(self, apps, fault=None):
        self.transports = {host: httpx.ASGITransport(app=app) for host, app in apps.items()}
        self.fault = fault
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append((request.method, request.url.host, request.url.path))
        if self.fault:
            response = self.fault(request)
            if response is not None:
                return response
        return await self.transports[request.url.host].handle_async_request(request)


@pytest.fixture
def transport(settings, app):
    return ServiceTransport({"business": app, "upstream": create_demo_app(settings)})


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://business",
        headers={"Authorization": f"Bearer {CLIENT_TOKEN}"},
    ) as client:
        yield client


ACTOR = "c23d7b4c-e0c9-4eee-a09c-35a8dfd7c7f4"


def draft_graph():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts/verification/build_flow.py"
    spec = importlib.util.spec_from_file_location("verification_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_payload()["data"]


def seed_release(database, settings, graph=None):
    from langflow.verification.database import fingerprint

    graph = graph or draft_graph()
    for node in graph["nodes"]:
        if node["data"]["type"].endswith("VerificationSettlementSnapshot@extra"):
            node["data"]["node"]["template"]["page_size"]["value"] = 1
    seed_demo(database)
    with database.sessions.begin() as session:
        rule = session.get(RuleDefinition, "high_value_consumables")
        if rule is None:
            rule = RuleDefinition(
                code="high_value_consumables", name="高值耗材智能体", flow_id=str(uuid4()), owner_id=ACTOR
            )
            session.add(rule)
            session.flush()
        package = compile_release(
            graph,
            {"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"},
            settings,
            flow_id=rule.flow_id,
            owner_id=ACTOR,
        )
        candidate = ReleaseCandidate(
            rule_code=rule.code,
            package=package,
            content_hash=fingerprint(package),
            author_id=ACTOR,
            validation={"structure": "passed", "simulation": "passed"},
            note="test",
        )
        session.add(candidate)
        session.flush()
        release = publish(
            session, rule, PublishRelease(candidate_id=candidate.id, content_hash=candidate.content_hash), ACTOR
        )
        activate(session, rule, ActivateRelease(release_id=release.id, expected_revision=rule.revision), ACTOR)
        return release
