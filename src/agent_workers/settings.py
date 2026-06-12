"""CT104 worker settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerSettings:
    redis_url: str
    agent_runs_dir: Path
    agent_cache_dir: Path
    agent_state_root: Path
    gitea_base_url: str
    gitea_agent_token: str
    gitea_agent_comment_enabled: bool
    git_ro_key_path: Path | None
    model_policy: str


def get_worker_settings() -> WorkerSettings:
    runs = Path(os.environ.get("AGENT_RUNS_DIR", "/mnt/agent-runs"))
    cache = Path(os.environ.get("AGENT_CACHE_DIR", "/mnt/agent-cache"))
    state = Path(os.environ.get("AGENT_STATE_ROOT", "/data/agent-state"))
    key_path = os.environ.get("GIT_RO_KEY_PATH", "/run/secrets/git_ro_key")
    return WorkerSettings(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        agent_runs_dir=runs,
        agent_cache_dir=cache,
        agent_state_root=state,
        gitea_base_url=os.environ.get("GITEA_BASE_URL", "https://git.ham-sup-lo.com"),
        gitea_agent_token=os.environ.get("GITEA_AGENT_TOKEN", ""),
        gitea_agent_comment_enabled=os.environ.get("GITEA_AGENT_COMMENT_ENABLED", "").lower()
        in ("1", "true", "yes"),
        git_ro_key_path=Path(key_path) if key_path else None,
        model_policy=os.environ.get("MODEL_ROUTING_POLICY", "fake"),
    )
