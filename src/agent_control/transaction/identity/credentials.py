"""CT104 durable-credential absence helper (TB1 library-level)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

FORBIDDEN_ENV_NAMES = (
    "GITEA_BOT_TOKEN",
    "GITEA_AGENT_TOKEN",
    "BROKER_SIGNING_SECRET",
    "DURABLE_CAPABILITY_SIGNING_SECRET",
    "DEPLOY_SSH_KEY",
    "DEPLOY_CT104_SSH_KEY",
)
FORBIDDEN_ENV_PREFIXES = ("DEPLOY_",)


def worker_credential_assertion(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Assert WORKER_DURABLE_CREDENTIALS_PRESENT=NO. Does not implement a live push."""
    source = env if env is not None else os.environ
    violations: list[dict[str, str]] = []
    for name in FORBIDDEN_ENV_NAMES:
        if source.get(name):
            violations.append({"code": "FORBIDDEN_ENV_PRESENT", "env_name": name})
    for key, value in source.items():
        if not value:
            continue
        if key in FORBIDDEN_ENV_NAMES:
            continue
        if any(key.startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES):
            violations.append({"code": "FORBIDDEN_ENV_PRESENT", "env_name": key})
    present = "YES" if violations else "NO"
    return {
        "schema_version": "worker_credential_assertion.v1",
        "host_role": "CT104",
        "WORKER_DURABLE_CREDENTIALS_PRESENT": present,
        "forbidden_env_names": list(FORBIDDEN_ENV_NAMES),
        "fail_closed": True,
        "this_file_is_runtime_result": True,
        "ok": present == "NO",
        "violations": violations,
        "notes": "Library helper. Live Gitea push is out of scope for this package.",
    }
