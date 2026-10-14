"""Gate local intake before a restart. Credentials never appear in commands or output."""

import argparse
import time
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

from langflow.business.maintenance import change, status
from langflow.business.models import initialize
from langflow.verification.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["close", "open", "status"])
    parser.add_argument("--wait", type=int, default=0)
    args = parser.parse_args()
    config = dotenv_values(Path(__file__).resolve().parents[2] / "deploy/verification/.env")
    db = Database("postgresql+psycopg://verification_app:" + quote(config["VERIFICATION_DB_PASSWORD"], safe="")
                  + "@127.0.0.1:55433/verification", "verification_scope")
    initialize(db)
    try:
        state = status(db) if args.action == "status" else change(db, args.action)
        deadline = time.monotonic() + args.wait
        while args.action == "close" and state["pending_tasks"] and time.monotonic() < deadline:
            print(f"Intake paused; waiting for {len(state['pending_tasks'])} accepted local tasks", flush=True)
            time.sleep(2)
            state = status(db)
        if args.action == "close" and not state["safe_to_upgrade"]:
            raise SystemExit("Accepted tasks have not drained. Existing services were left running; do not upgrade yet.")
        print(f"Task intake: {state['status']}; pending local tasks: {len(state['pending_tasks'])}")
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
