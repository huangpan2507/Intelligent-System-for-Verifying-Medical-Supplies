"""Run one source-based demo service using the private credentials and existing UI database."""

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["init", "platform", "api", "demo", "core-demo", "worker"])
    args = parser.parse_args()
    private = ROOT / "deploy/verification/.env"
    if not private.is_file():
        parser.error("Run scripts/verification/configure_demo.py first")
    config = dotenv_values(private)
    api_port = int(config.get("VERIFICATION_SOURCE_API_PORT") or "8081")
    os.environ.update({key: value for key, value in config.items() if value is not None})
    platform_config = ROOT / "deploy/verification/.cache/source-ui"
    platform_config.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        LANGFLOW_CONFIG_DIR=str(platform_config),
        VERIFICATION_API_URL=f"http://127.0.0.1:{api_port}",
        VERIFICATION_SETTLEMENT_URL="http://127.0.0.1:8090",
        VERIFICATION_IMAGING_URL="http://127.0.0.1:8090",
        VERIFICATION_MODEL_URL="http://127.0.0.1:8090",
        VERIFICATION_DEMO_MODE="true",
        VERIFICATION_LANGFLOW_URL="http://127.0.0.1:7860",
        VERIFICATION_DATABASE_URL=(
            "postgresql+psycopg://verification_app:"
            f"{quote(config['VERIFICATION_DB_PASSWORD'], safe='')}@127.0.0.1:55433/verification"
        ),
        VERIFICATION_DATABASE_SCHEMA="verification_scope",
    )
    if args.service == "init":
        from langflow.verification.database import Database
        from langflow.verification.settings import VerificationSettings

        settings = VerificationSettings()
        database = Database(settings.database_url.get_secret_value(), settings.database_schema)
        database.initialize()
        from langflow.verification.demo import seed_demo

        seed_demo(database)
        database.engine.dispose()
        print("Business schema ready in PostgreSQL at 127.0.0.1:55433")
        return
    if args.service == "worker":
        from langflow.verification.worker import serve

        print("Single worker listening for accepted tasks", flush=True)
        asyncio.run(serve())
        return
    if args.service == "platform":
        os.environ.update(
            LANGFLOW_DATABASE_URL=f"sqlite:///{platform_config / 'langflow.db'}",
            LANGFLOW_COMPONENTS_PATH=str(ROOT / "deploy/verification/components"),
            LANGFLOW_SUPERUSER="verification-admin",
            LANGFLOW_AUTO_LOGIN="false",
            LANGFLOW_CREATE_STARTER_PROJECTS="false",
            LANGFLOW_UPDATE_STARTER_PROJECTS="false",
            LANGFLOW_LAZY_LOAD_COMPONENTS="true",
            LANGFLOW_SKIP_MCP_AUTO_INIT="true",
            LANGFLOW_MODELS_DEV_REFRESH="false",
            LANGFLOW_DO_NOT_TRACK="true",
        )
    import uvicorn

    services = {
        "platform": ("langflow.main:create_app", 7860),
        "api": ("langflow.verification.api:create_app", api_port),
        "demo": ("langflow.verification.demo:create_demo_app", 8090),
        "core-demo": ("langflow.business.core_flow_demo:create_core_flow_app", 8091),
    }
    app, port = services[args.service]
    uvicorn.run(app, factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
