"""Log into a local demo Langflow, create its worker key, and import the reviewed flow."""

import argparse
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLOW_FILE = ROOT / "deploy/verification/consumable-verification-palette.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7860")
    args = parser.parse_args()
    env_file = ROOT / "deploy/verification/.env"
    config = dotenv_values(env_file)
    with httpx.Client(base_url=args.url, timeout=60) as http:
        response = http.post(
            "/api/v1/login", data={"username": "verification-admin", "password": config["LANGFLOW_SUPERUSER_PASSWORD"]}
        )
        response.raise_for_status()
        http.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        if not config.get("VERIFICATION_LANGFLOW_API_KEY"):
            response = http.post("/api/v1/api_key/", json={"name": "consumable-verification-worker"})
            response.raise_for_status()
            set_key(env_file, "VERIFICATION_LANGFLOW_API_KEY", response.json()["api_key"])
        with DEFAULT_FLOW_FILE.open("rb") as file:
            response = http.post(
                "/api/v1/flows/upload/", files={"file": ("verification.json", file, "application/json")}
            )
        response.raise_for_status()
        flow = response.json()[0]
        set_key(env_file, "VERIFICATION_FLOW_ID", str(flow["id"]))
        env_file.chmod(0o600)
        print(f"Imported flow {flow['id']}; worker credential saved privately to {env_file}")


if __name__ == "__main__":
    main()
