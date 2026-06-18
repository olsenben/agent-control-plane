"""Typed settings for the control plane."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gitea_base_url: str = Field(default="http://gitea.local:3000", alias="GITEA_BASE_URL")
    gitea_bot_token: str = Field(default="", alias="GITEA_BOT_TOKEN")
    gitea_webhook_secret: str = Field(default="", alias="GITEA_WEBHOOK_SECRET")
    gitea_allowed_repos: str = Field(
        default="ai-sdlc-lab/*",
        alias="GITEA_ALLOWED_REPOS",
        description="Comma-separated owner/repo allowlist; owner/* or * wildcards supported",
    )
    agent_state_root: Path = Field(
        default=Path("../agent-state"),
        alias="AGENT_STATE_ROOT",
    )
    agent_runs_dir: Path = Field(default=Path("/mnt/agent-runs"), alias="AGENT_RUNS_DIR")
    agent_cache_dir: Path = Field(default=Path("/mnt/agent-cache"), alias="AGENT_CACHE_DIR")
    gitea_agent_token: str = Field(default="", alias="GITEA_AGENT_TOKEN")
    gitea_agent_comment_enabled: bool = Field(default=False, alias="GITEA_AGENT_COMMENT_ENABLED")
    queue_prefix: str = Field(default="", alias="QUEUE_PREFIX")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    model_3080_base_url: str = Field(default="", alias="MODEL_3080_BASE_URL")
    model_3080_name: str = Field(default="", alias="MODEL_3080_NAME")
    model_3080_api_key: str = Field(default="", alias="MODEL_3080_API_KEY")
    model_2070_base_url: str = Field(default="", alias="MODEL_2070_BASE_URL")
    model_2070_name: str = Field(default="", alias="MODEL_2070_NAME")
    model_2070_api_key: str = Field(default="", alias="MODEL_2070_API_KEY")
    model_3080_external_base_url: str = Field(default="", alias="MODEL_3080_EXTERNAL_BASE_URL")
    model_3080_external_name: str = Field(default="", alias="MODEL_3080_EXTERNAL_NAME")
    model_3080_external_api_key: str = Field(default="", alias="MODEL_3080_EXTERNAL_API_KEY")
    model_2070_external_base_url: str = Field(default="", alias="MODEL_2070_EXTERNAL_BASE_URL")
    model_2070_external_name: str = Field(default="", alias="MODEL_2070_EXTERNAL_NAME")
    model_2070_external_api_key: str = Field(default="", alias="MODEL_2070_EXTERNAL_API_KEY")
    model_3080_fallback_base_url: str = Field(default="", alias="MODEL_3080_FALLBACK_BASE_URL")
    model_3080_fallback_name: str = Field(default="", alias="MODEL_3080_FALLBACK_NAME")
    model_3080_fallback_api_key: str = Field(default="", alias="MODEL_3080_FALLBACK_API_KEY")
    model_2070_fallback_base_url: str = Field(default="", alias="MODEL_2070_FALLBACK_BASE_URL")
    model_2070_fallback_name: str = Field(default="", alias="MODEL_2070_FALLBACK_NAME")
    model_2070_fallback_api_key: str = Field(default="", alias="MODEL_2070_FALLBACK_API_KEY")
    model_external_roles: str = Field(
        default="",
        alias="MODEL_EXTERNAL_ROLES",
        description="Comma-separated roles that prefer external tier endpoints when configured",
    )
    model_fallback_enabled: bool = Field(default=True, alias="MODEL_FALLBACK_ENABLED")
    model_health_timeout_seconds: float = Field(default=3.0, alias="MODEL_HEALTH_TIMEOUT_SECONDS")
    model_health_required_for_readyz: bool = Field(
        default=False,
        alias="MODEL_HEALTH_REQUIRED_FOR_READYZ",
        description="If true, unreachable GPUs make /readyz return 503 (same as strict=true)",
    )
    enforce_public_surface_restriction: bool = Field(
        default=False,
        alias="ENFORCE_PUBLIC_SURFACE_RESTRICTION",
        description="If true, only /healthz, /readyz, /webhooks/gitea are served",
    )
    model_routing_policy: str = Field(
        default="fake",
        alias="MODEL_ROUTING_POLICY",
        description="Platform-owned engine selection passed to CT104 jobs (fake, official, local, ...)",
    )
    graph_snapshot_repos: str = Field(
        default="",
        alias="GRAPH_SNAPSHOT_REPOS",
        description="Optional comma-separated owner/repo override for graph snapshot (tests)",
    )

    @property
    def graph_db_path(self) -> Path:
        return self.agent_state_root / "graph" / "graph.sqlite"

    @property
    def graph_export_dir(self) -> Path:
        return self.agent_state_root / "graph" / "exports"

    @property
    def graph_snapshot_cache(self) -> Path:
        return self.agent_cache_dir / "graph-snapshots"

    def graph_snapshot_repos_list(self) -> list[str] | None:
        items = [r.strip() for r in self.graph_snapshot_repos.split(",") if r.strip()]
        return items or None

    def allowed_repos_set(self) -> set[str]:
        return {r.strip() for r in self.gitea_allowed_repos.split(",") if r.strip()}

    def is_repo_allowed(self, full_name: str) -> bool:
        """Match owner/repo entries; owner/* allows any repo under that owner; * allows all."""
        if not full_name or "/" not in full_name:
            return False
        owner, _repo = full_name.split("/", 1)
        for pattern in self.allowed_repos_set():
            if pattern == "*":
                return True
            if pattern.endswith("/*"):
                if owner == pattern[:-2]:
                    return True
            elif pattern == full_name:
                return True
        return False

    def external_roles_set(self) -> set[str]:
        return {r.strip() for r in self.model_external_roles.split(",") if r.strip()}


def get_settings() -> Settings:
    return Settings()
