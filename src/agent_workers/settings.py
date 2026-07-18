"""CT104 worker settings — fail closed if Gitea write tokens are present."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class WorkerCredentialError(RuntimeError):
    """Raised when CT104 is configured with forbidden Gitea write credentials."""


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


def get_worker_settings() -> WorkerSettings:
    runs = Path(os.environ.get("AGENT_RUNS_DIR", "/mnt/agent-runs"))
    cache = Path(os.environ.get("AGENT_CACHE_DIR", "/mnt/agent-cache"))
    state = Path(os.environ.get("AGENT_STATE_ROOT", "/data/agent-state"))
    key_path = os.environ.get("GIT_RO_KEY_PATH", "/run/secrets/git_ro_key")
    publish = _truthy("FIX_REMOTE_PUBLISH_ENABLED")
    agent_token = os.environ.get("GITEA_AGENT_TOKEN", "")
    bot_token = os.environ.get("GITEA_BOT_TOKEN", "")

    # Production fail-closed: CT104 must not hold write tokens (V4.1.1)
    allow_debt = _truthy("CT104_ALLOW_WRITE_TOKEN_DEBT")
    if not allow_debt and (agent_token or bot_token):
        raise WorkerCredentialError(
            "CT104 must not have GITEA_AGENT_TOKEN or GITEA_BOT_TOKEN "
            "(V4.1.1 publish brokerage). Unset them or set CT104_ALLOW_WRITE_TOKEN_DEBT=1 "
            "only for emergency rollback."
        )

    return WorkerSettings(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        agent_runs_dir=runs,
        agent_cache_dir=cache,
        agent_state_root=state,
        gitea_base_url=os.environ.get("GITEA_BASE_URL", "https://git.ham-sup-lo.com"),
        gitea_agent_token=agent_token,
        gitea_bot_token=bot_token,
        gitea_agent_comment_enabled=_truthy("GITEA_AGENT_COMMENT_ENABLED"),
        git_ro_key_path=Path(key_path) if key_path else None,
        model_policy=os.environ.get("MODEL_ROUTING_POLICY", "fake"),
        fix_remote_publish_enabled=publish,
    )
