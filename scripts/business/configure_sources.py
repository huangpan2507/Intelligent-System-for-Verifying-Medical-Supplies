"""Create private demo-source credentials once; do not print or replace them."""

import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "deploy/verification/.cache/business-sources.env"
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists():
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("BUSINESS_DB_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
print("Private demo-source configuration ready")
