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
        default="ai-sdlc-lab/demo-app",
        alias="GITEA_ALLOWED_REPOS",
        description="Comma-separated owner/repo allowlist",
    )
    agent_state_root: Path = Field(
        default=Path("../agent-state"),
        alias="AGENT_STATE_ROOT",
    )
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

    def allowed_repos_set(self) -> set[str]:
        return {r.strip() for r in self.gitea_allowed_repos.split(",") if r.strip()}

    def external_roles_set(self) -> set[str]:
        return {r.strip() for r in self.model_external_roles.split(",") if r.strip()}


def get_settings() -> Settings:
    return Settings()
