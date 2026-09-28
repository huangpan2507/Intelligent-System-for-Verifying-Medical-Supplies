"""Submit a synthetic task and query saved results without triggering re-execution."""

import argparse
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from langflow.verification.demo import example_task

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--reference", default="demo-001")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output-dir", type=Path, help="Save this run's request, result and evidence JSON")
    args = parser.parse_args()
    config = dotenv_values(ROOT / "deploy/verification/.env")
    token = json.loads(config["VERIFICATION_CLIENTS"])["demo-regulator"]
    with httpx.Client(base_url=args.url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as http:
        task = example_task(args.reference)
        response = http.post("/api/v1/verification/tasks", json=task)
        response.raise_for_status()
        accepted = response.json()
        print(json.dumps(accepted, ensure_ascii=False, indent=2), flush=True)
        deadline = time.monotonic() + args.timeout
        previous = None
        while time.monotonic() < deadline:
            response = http.get(
                f"/api/v1/verification/tasks/{accepted['task_id']}/results", params={"run_id": accepted["run_id"]}
            )
            response.raise_for_status()
            value = response.json()
            current = (value["status"], value["stage"], value["stage_event"])
            if current != previous:
                print(f"status={current[0]} stage={current[1]} event={current[2]}", flush=True)
                previous = current
            if value["status"] not in {"waiting", "running"}:
                print(json.dumps(value, ensure_ascii=False, indent=2))
                if args.output_dir:
                    response = http.get(
                        f"/api/v1/verification/tasks/{accepted['task_id']}/evidence",
                        params={"run_id": accepted["run_id"]},
                    )
                    response.raise_for_status()
                    target = args.output_dir / accepted["run_id"]
                    target.mkdir(parents=True, exist_ok=True)
                    for name, data in {"request": task, "result": value, "evidence": response.json()}.items():
                        (target / f"{name}.json").write_text(
                            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                        )
                    print(f"Saved run snapshot to {target.resolve()}")
                if value["status"] != "completed" or not value["available"]:
                    msg = "Run did not complete successfully; inspect its saved status before any rerun"
                    raise SystemExit(msg)
                return
            time.sleep(1)
    msg = "Result is still pending; inspect the existing task. Do not automatically resubmit."
    raise SystemExit(msg)


if __name__ == "__main__":
    main()
