import httpx
import pytest
from langflow.verification.api import create_app
from langflow.verification.database import Database
from langflow.verification.demo import create_demo_app
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
        catalog_mapping={"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"},
    )


@pytest.fixture
def database(settings):
    db = Database(settings.database_url.get_secret_value())
    db.initialize()
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
