"""Create private demo credentials without printing secrets or overwriting existing configuration."""

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def configure() -> Path:
    target = ROOT / "deploy/verification/.env"
    values = {
        name: secrets.token_urlsafe(32)
        for name in (
            "POSTGRES_PASSWORD",
            "PLATFORM_DB_PASSWORD",
            "VERIFICATION_DB_PASSWORD",
            "LANGFLOW_SUPERUSER_PASSWORD",
            "LANGFLOW_SECRET_KEY",
            "VERIFICATION_INTERNAL_TOKEN",
            "VERIFICATION_UPSTREAM_TOKEN",
        )
    }
    values["VERIFICATION_CLIENTS"] = json.dumps({"demo-regulator": secrets.token_urlsafe(32)}, separators=(",", ":"))
    values["VERIFICATION_LANGFLOW_API_KEY"] = ""
    values["VERIFICATION_FLOW_ID"] = "consumable-verification"
    with target.open("x", encoding="utf-8") as file:
        target.chmod(0o600)
        file.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    return target


if __name__ == "__main__":
    print(configure())
