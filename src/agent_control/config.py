"""Typed settings for the control plane."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gitea_base_url: str = Field(default="http://gitea.local:3000", alias="GITEA_BASE_URL")
    gitea_bot_token: str = Field(default="", alias="GITEA_BOT_TOKEN")
    gitea_acting_identity: str = Field(
        default="agent-bot",
        alias="GITEA_ACTING_IDENTITY",
        description=(
            "Gitea login for the bot principal that owns GITEA_BOT_TOKEN "
            "(acting_identity on sessions/comments; never the human invoker)"
        ),
    )
    gitea_webhook_secret: str = Field(default="", alias="GITEA_WEBHOOK_SECRET")
    gitea_allowed_repos: str = Field(
        default="ai-sdlc-lab/*",
        alias="GITEA_ALLOWED_REPOS",
        description="Comma-separated owner/repo allowlist; owner/* or * wildcards supported",
    )
    gitea_approver_logins: str = Field(
        default="",
        alias="GITEA_APPROVER_LOGINS",
        description=(
            "Comma-separated Gitea logins allowed to /agent approve and /agent reject "
            "(in addition to owner/repo namespace segment match)"
        ),
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
    model_gateway_base_url: str = Field(
        default="",
        alias="MODEL_GATEWAY_BASE_URL",
        description="CT103 LiteLLM proxy OpenAI-compatible base URL; CT104 should call this only",
    )
    model_gateway_api_key: str = Field(default="", alias="MODEL_GATEWAY_API_KEY")
    model_gateway_model_map: str = Field(
        default="",
        alias="MODEL_GATEWAY_MODEL_MAP",
        description="Optional role=alias map, e.g. planner=primary-generator,worker=context-controller",
    )
    repo_external_model_policy: str = Field(
        default="",
        alias="REPO_EXTERNAL_MODEL_POLICY",
        description="Comma-separated owner/repo allowlist for external model egress; empty=deny all",
    )
    model_code_handling_roles: str = Field(
        default="fixer,rlm",
        alias="MODEL_CODE_HANDLING_ROLES",
        description="Roles allowed to send code-bearing prompts to external providers when egress permits",
    )
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
    observe_require_auth: bool = Field(
        default=True,
        alias="OBSERVE_REQUIRE_AUTH",
        description="V6 T03: require repo-read auth on all Observatory surfaces (fail closed)",
    )
    observe_shared_token: str | None = Field(
        default=None,
        alias="OBSERVE_SHARED_TOKEN",
        description="Optional shared bearer token that grants Observatory read access",
    )
    observe_oauth_client_id: str | None = Field(
        default=None,
        alias="OBSERVE_OAUTH_CLIENT_ID",
        description="V8 T04: Gitea OAuth application client id (CT103 secret; empty until human registers app)",
    )
    observe_oauth_client_secret: str | None = Field(
        default=None,
        alias="OBSERVE_OAUTH_CLIENT_SECRET",
        description="V8 T04: Gitea OAuth application client secret (CT103 only; never commit)",
    )
    observe_oauth_redirect_uri: str | None = Field(
        default=None,
        alias="OBSERVE_OAUTH_REDIRECT_URI",
        description="V8 T04: registered redirect URI (e.g. http://192.168.4.62:8080/observe/oauth/callback)",
    )
    model_routing_policy: str = Field(
        default="fake",
        alias="MODEL_ROUTING_POLICY",
        description="Platform-owned engine selection passed to CT104 jobs (fake, official, local, ...)",
    )
    fix_remote_publish_enabled: bool = Field(
        default=False,
        alias="FIX_REMOTE_PUBLISH_ENABLED",
        description="Slice 6D: enable agent branch push + PR after diff gate pass",
    )
    fix_ci_observe_enabled: bool = Field(
        default=False,
        alias="FIX_CI_OBSERVE_ENABLED",
        description="Slice 6E.1: observe/correlate/aggregate CT102 workflow runs for agent PRs",
    )
    fix_ci_require_matrix_match: bool = Field(
        default=True,
        alias="FIX_CI_REQUIRE_MATRIX_MATCH",
        description="Slice 6E.1: enforce required_workflows from matrix / repo default",
    )
    fix_ci_repo_default_workflow: str = Field(
        default=".gitea/workflows/ci.yaml",
        alias="FIX_CI_REPO_DEFAULT_WORKFLOW",
        description="Repo-default CI workflow path when matrix is empty and require_matrix=true",
    )
    fix_ci_failure_evidence_enabled: bool = Field(
        default=False,
        alias="FIX_CI_FAILURE_EVIDENCE_ENABLED",
        description="Slice 6F.1: pull CT102 job logs and persist failure evidence",
    )
    fix_ci_repair_enabled: bool = Field(
        default=False,
        alias="FIX_CI_REPAIR_ENABLED",
        description="Slice 6F.2: gated automatic repair (requires observe + evidence)",
    )
    fix_ci_repair_max_attempts: int = Field(
        default=1,
        alias="FIX_CI_REPAIR_MAX_ATTEMPTS",
        description="Automatic repair attempts per repair lineage (v1 default 1)",
    )
    fix_ci_repair_allowed_repos: str = Field(
        default="",
        alias="FIX_CI_REPAIR_ALLOWED_REPOS",
        description=(
            "Exact owner/repo allowlist for automatic repair (comma-separated). "
            "No wildcards. Empty = deny all."
        ),
    )
    fix_ci_repair_allowed_classes: str = Field(
        default="lint_failure",
        alias="FIX_CI_REPAIR_ALLOWED_CLASSES",
        description="Comma-separated failure classes eligible for auto-repair",
    )
    fix_ci_repair_publish_enabled: bool = Field(
        default=False,
        alias="FIX_CI_REPAIR_PUBLISH_ENABLED",
        description="Stage 3: allow CT103 brokerage publication for repair bundles",
    )
    sandbox_backend: str = Field(
        default="srt",
        alias="SANDBOX_BACKEND",
        description="OS sandbox backend id (srt); nested/weak mode never accepted",
    )
    sandbox_expected_policy_hash: str = Field(
        default="",
        alias="SANDBOX_EXPECTED_POLICY_HASH",
        description="Required policy_hash for strong sandbox attestation",
    )
    sandbox_require_attestation: bool = Field(
        default=True,
        alias="SANDBOX_REQUIRE_ATTESTATION",
        description="Risk 2 / repair require strong attestation when true",
    )
    graph_snapshot_repos: str = Field(
        default="",
        alias="GRAPH_SNAPSHOT_REPOS",
        description="Optional comma-separated owner/repo override for graph snapshot (tests)",
    )
    agentfacts_signing_secret: str = Field(
        default="",
        alias="AGENTFACTS_SIGNING_SECRET",
        description=(
            "Optional HMAC secret for AgentFacts-lite manifests. "
            "Empty = content-hash integrity only (digest + source hashes)."
        ),
    )
    memory_governance_repeated_threshold: int = Field(
        default=2,
        alias="MEMORY_GOVERNANCE_REPEATED_THRESHOLD",
        description=(
            "Deny /agent fix when memory has this many failed attempts "
            "of the same failure_class (overlapping files) without new evidence"
        ),
    )
    memory_governance_trajectory_limit: int = Field(
        default=50,
        alias="MEMORY_GOVERNANCE_TRAJECTORY_LIMIT",
        description="Max memory records scanned for memory-as-governance",
    )

    @property
    def memory_db_path(self) -> Path:
        return self.agent_state_root / "memory" / "memory.sqlite"

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

    def approver_logins_set(self) -> set[str]:
        return {r.strip().lower() for r in self.gitea_approver_logins.split(",") if r.strip()}

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

    def repair_allowed_repos_list(self) -> list[str]:
        from agent_control.ci.repair_policy import parse_repair_allowlist

        return parse_repair_allowlist(self.fix_ci_repair_allowed_repos)

    def repair_allowed_classes_set(self) -> frozenset[str]:
        from agent_control.ci.repair_policy import parse_repair_classes

        return parse_repair_classes(self.fix_ci_repair_allowed_classes)

    def external_roles_set(self) -> set[str]:
        return {r.strip() for r in self.model_external_roles.split(",") if r.strip()}

    @model_validator(mode="after")
    def validate_fix_ci_flag_combo(self) -> Settings:
        if self.fix_ci_repair_enabled and not (
            self.fix_ci_observe_enabled and self.fix_ci_failure_evidence_enabled
        ):
            raise ValueError(
                "FIX_CI_REPAIR_ENABLED requires FIX_CI_OBSERVE_ENABLED and "
                "FIX_CI_FAILURE_EVIDENCE_ENABLED"
            )
        # Fail closed on invalid repair allowlist at startup
        from agent_control.ci.repair_policy import parse_repair_allowlist, parse_repair_classes

        parse_repair_allowlist(self.fix_ci_repair_allowed_repos)
        parse_repair_classes(self.fix_ci_repair_allowed_classes)
        return self


def get_settings() -> Settings:
    return Settings()
