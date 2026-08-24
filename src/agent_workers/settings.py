"""CT104 worker settings — fail closed if durable credentials are present."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable, Sequence

# Named product assertion: CT104 workers must not hold durable write/signing
# credentials. Invoked at process start (agentctl worker run) and from
# get_worker_settings(). CT104_ALLOW_WRITE_TOKEN_DEBT is not a product bypass.
WORKER_DURABLE_CREDENTIALS_PRESENT: Final[str] = "NO"

FORBIDDEN_DURABLE_ENV_NAMES: Final[tuple[str, ...]] = (
    "GITEA_BOT_TOKEN",
    "GITEA_AGENT_TOKEN",
    "GITEA_WEBHOOK_SECRET",
    "AGENTFACTS_SIGNING_SECRET",
    "OBSERVE_SHARED_TOKEN",
    "OBSERVE_OAUTH_CLIENT_SECRET",
    "BROKER_SIGNING_SECRET",
    "DURABLE_CAPABILITY_SIGNING_SECRET",
    "DEPLOY_SSH_KEY",
    "DEPLOY_CT104_SSH_KEY",
)

FORBIDDEN_DURABLE_ENV_PREFIXES: Final[tuple[str, ...]] = ("DEPLOY_",)

# Queues that run on CT104. CT103 publish-broker (queue "publish") and
# worker-state (state / results-ingest) must not hit this assertion.
CT104_WORKER_QUEUES: Final[frozenset[str]] = frozenset(
    {
        "rlm-root",
        "rlm-child",
        "report",
        "ci-repair",
        "verify",
    }
)

# Mounted on worker-rlm-root / worker-ci-repair for clone-only HTTPS.
# Presence of this file does not satisfy write-token absence and is not a
# GITEA_BOT_TOKEN substitute. Do not give workers GITEA_BOT_TOKEN.
GIT_CREDENTIALS_CLONE_ONLY_PATH: Final[Path] = Path("/root/.git-credentials")


class WorkerCredentialError(RuntimeError):
    """Raised when CT104 is configured with forbidden durable credentials."""


@dataclass(frozen=True)
class DurableCredentialViolation:
    code: str
    env_name: str


@dataclass(frozen=True)
class WorkerSettings:
    redis_url: str
    agent_runs_dir: Path
    agent_cache_dir: Path
    agent_state_root: Path
    gitea_base_url: str
    gitea_agent_token: str
    gitea_bot_token: str
    gitea_agent_comment_enabled: bool
    git_ro_key_path: Path | None
    model_policy: str
    fix_remote_publish_enabled: bool


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def _nonempty_env(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def collect_durable_credential_violations() -> list[DurableCredentialViolation]:
    """Return name-only violations. Never includes secret values."""
    violations: list[DurableCredentialViolation] = []
    flag = os.environ.get("WORKER_DURABLE_CREDENTIALS_PRESENT")
    if flag is not None and flag != WORKER_DURABLE_CREDENTIALS_PRESENT:
        violations.append(
            DurableCredentialViolation(
                code="WORKER_DURABLE_CREDENTIALS_PRESENT_NOT_NO",
                env_name="WORKER_DURABLE_CREDENTIALS_PRESENT",
            )
        )

    seen: set[str] = set()
    for name in FORBIDDEN_DURABLE_ENV_NAMES:
        if _nonempty_env(name) and name not in seen:
            seen.add(name)
            violations.append(
                DurableCredentialViolation(code="FORBIDDEN_ENV_PRESENT", env_name=name)
            )
    for key, value in os.environ.items():
        if not value.strip():
            continue
        if not any(key.startswith(prefix) for prefix in FORBIDDEN_DURABLE_ENV_PREFIXES):
            continue
        if key in seen:
            continue
        seen.add(key)
        violations.append(
            DurableCredentialViolation(code="FORBIDDEN_ENV_PRESENT", env_name=key)
        )
    return violations


def git_credentials_clone_only_note() -> str:
    """Document the git-credentials mount as clone-only; never log file contents.

    The assertion does not read ``GIT_CREDENTIALS_CLONE_ONLY_PATH``. Presence of
    that file does not satisfy write-token absence; env write tokens stay forbidden.
    """
    return (
        "git-credentials mount is clone-only and must not contain a write PAT; "
        "it does not satisfy write-token absence. Workers must not receive "
        f"GITEA_BOT_TOKEN. clone_only_path={GIT_CREDENTIALS_CLONE_ONLY_PATH}"
    )


def assert_worker_durable_credentials_absent() -> None:
    """Fail closed unless WORKER_DURABLE_CREDENTIALS_PRESENT=NO holds.

    CT104_ALLOW_WRITE_TOKEN_DEBT is ignored. A clone-only git-credentials
    file, if present, does not permit env write tokens.
    """
    violations = collect_durable_credential_violations()
    if not violations:
        return
    names = ", ".join(v.env_name for v in violations)
    raise WorkerCredentialError(
        "WORKER_DURABLE_CREDENTIALS_PRESENT=NO fail-closed: durable credentials "
        f"must be absent on CT104 workers. Unset: {names}. "
        f"{git_credentials_clone_only_note()}"
    )


def assert_ct104_worker_process_credentials(queues: Sequence[str] | None = None) -> None:
    """Invoke the durable-credential assertion for CT104 worker processes.

    Called from ``agentctl worker run``. CT103 publish-broker and worker-state
    skip unless WORKER_DURABLE_CREDENTIALS_PRESENT is set (CT104 compose
    forces NO so a copied .env cannot skip the check).
    """
    flag = os.environ.get("WORKER_DURABLE_CREDENTIALS_PRESENT")
    queue_names: Iterable[str] = queues or ()
    if flag is None and not CT104_WORKER_QUEUES.intersection(queue_names):
        return
    assert_worker_durable_credentials_absent()


def get_worker_settings() -> WorkerSettings:
    assert_worker_durable_credentials_absent()

    runs = Path(os.environ.get("AGENT_RUNS_DIR", "/mnt/agent-runs"))
    cache = Path(os.environ.get("AGENT_CACHE_DIR", "/mnt/agent-cache"))
    state = Path(os.environ.get("AGENT_STATE_ROOT", "/data/agent-state"))
    key_path = os.environ.get("GIT_RO_KEY_PATH", "/run/secrets/git_ro_key")
    publish = _truthy("FIX_REMOTE_PUBLISH_ENABLED")

    return WorkerSettings(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        agent_runs_dir=runs,
        agent_cache_dir=cache,
        agent_state_root=state,
        gitea_base_url=os.environ.get("GITEA_BASE_URL", "https://git.ham-sup-lo.com"),
        gitea_agent_token="",
        gitea_bot_token="",
        gitea_agent_comment_enabled=_truthy("GITEA_AGENT_COMMENT_ENABLED"),
        git_ro_key_path=Path(key_path) if key_path else None,
        model_policy=os.environ.get("MODEL_ROUTING_POLICY", "fake"),
        fix_remote_publish_enabled=publish,
    )
