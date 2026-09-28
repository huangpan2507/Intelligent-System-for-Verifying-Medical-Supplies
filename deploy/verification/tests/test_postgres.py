import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from conftest import CLIENT_TOKEN
from fastapi.testclient import TestClient
from langflow.verification.api import create_app
from langflow.verification.database import Database, Run, Task
from langflow.verification.demo import example_task
from sqlalchemy import select
from sqlalchemy.schema import DropSchema


@pytest.mark.postgres
def test_postgres_concurrent_acceptance_and_claim(settings):
    url = os.getenv("VERIFICATION_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set VERIFICATION_TEST_POSTGRES_URL to exercise PostgreSQL transactions")
    schema = "verification_test_" + uuid4().hex
    database = Database(url, schema)
    database.initialize()
    app = create_app(settings, database)

    def submit(_):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/verification/tasks", json=example_task(), headers={"Authorization": f"Bearer {CLIENT_TOKEN}"}
            )
            assert response.status_code == 202, response.text
            return response.json()

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(submit, range(16)))
        assert len({item["task_id"] for item in accepted}) == 1
        with database.sessions() as session:
            assert len(list(session.scalars(select(Task)))) == 1
            assert len(list(session.scalars(select(Run)))) == 1
        with ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(lambda _: database.claim(), range(16)))
        assert [value for value in claimed if value is not None] == [accepted[0]["run_id"]]
        assert database.claim() is None
    finally:
        with database.engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        database.engine.dispose()
