"""CT104 worker settings — fail closed if durable credentials are present."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable, Sequence
from urllib.parse import unquote, urlparse

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

# SHA-256 (hex) of known write PATs that must never appear in the clone helper.
# Comma or whitespace separated. Never put the token itself in this variable.
FORBIDDEN_GIT_TOKEN_HASH_ENV: Final[str] = "CT104_FORBIDDEN_GIT_TOKEN_SHA256"
_SHA256_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


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


def _forbidden_git_token_hashes() -> set[str]:
    raw = os.environ.get(FORBIDDEN_GIT_TOKEN_HASH_ENV, "")
    hashes: set[str] = set()
    for part in re.split(r"[\s,]+", raw.strip()):
        if not part:
            continue
        digest = part.strip().lower()
        if _SHA256_HEX_RE.fullmatch(digest):
            hashes.add(digest)
    return hashes


def _git_credentials_password_hashes(path: Path) -> list[str]:
    """Return SHA-256 hex of stored passwords. Never returns secret values."""
    digests: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed = urlparse(stripped)
        password = unquote(parsed.password or "")
        if not password:
            continue
        digests.append(hashlib.sha256(password.encode("utf-8")).hexdigest())
    return digests


def collect_clone_helper_violations() -> list[DurableCredentialViolation]:
    """Fail closed on write-capable clone helpers. Never logs secret values.

    Git ``credential.helper=store`` will offer the stored secret for fetch and
    push. Env-only PASS cannot hide a write PAT in that file.
    """
    violations: list[DurableCredentialViolation] = []
    path = GIT_CREDENTIALS_CLONE_ONLY_PATH
    try:
        present = path.is_file()
    except OSError:
        return violations
    if not present:
        return violations
    try:
        writable = os.access(path, os.W_OK)
        denylist = _forbidden_git_token_hashes()
        digests = _git_credentials_password_hashes(path)
    except OSError:
        violations.append(
            DurableCredentialViolation(
                code="UNREADABLE_GIT_CREDENTIALS_STORE",
                env_name="GIT_CREDENTIALS_CLONE_ONLY_PATH",
            )
        )
        return violations
    if writable:
        violations.append(
            DurableCredentialViolation(
                code="WRITABLE_GIT_CREDENTIALS_STORE",
                env_name="GIT_CREDENTIALS_CLONE_ONLY_PATH",
            )
        )
    if not denylist:
        violations.append(
            DurableCredentialViolation(
                code="HTTPS_STORE_UNVERIFIED",
                env_name=FORBIDDEN_GIT_TOKEN_HASH_ENV,
            )
        )
        return violations
    if any(digest in denylist for digest in digests):
        violations.append(
            DurableCredentialViolation(
                code="FORBIDDEN_TOKEN_IN_CLONE_HELPER",
                env_name="GIT_CREDENTIALS_CLONE_ONLY_PATH",
            )
        )
    return violations


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
    violations.extend(collect_clone_helper_violations())
    return violations


def git_credentials_clone_only_note() -> str:
    """Document the git-credentials mount; never log file contents.

    The assertion inspects helper presence and password hashes against
    ``CT104_FORBIDDEN_GIT_TOKEN_SHA256``. Env write tokens stay forbidden.
    """
    return (
        "git-credentials mount is a clone helper and is inspected; a write PAT "
        "in that file is a fail-closed violation even when env tokens are absent. "
        "Workers must not receive GITEA_BOT_TOKEN. "
        f"clone_only_path={GIT_CREDENTIALS_CLONE_ONLY_PATH}"
    )


def assert_worker_durable_credentials_absent() -> None:
    """Fail closed unless WORKER_DURABLE_CREDENTIALS_PRESENT=NO holds.

    CT104_ALLOW_WRITE_TOKEN_DEBT is ignored. A git-credentials store, if
    present, is inspected; env-only PASS cannot hide a write-capable helper.
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
