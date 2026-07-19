"""Policy loading artifacts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_shared.models.jobs import JobSafety


class PolicySource(BaseModel):
    schema_version: str = "policy_source.v1"
    source: str = "repo"
    policy_ref: str
    policy_sha: str | None = None
    policy_source_repo: str | None = None
    policy_source_remote: str | None = None
    policy_source_ref: str | None = None
    policy_source_sha: str | None = None
    policy_schema_version: str | None = None
    task_ref: str | None = None
    task_sha: str | None = None
    loaded_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EffectivePolicy(BaseModel):
    schema_version: str = "effective_policy.v1"
    run_id: str
    flow: str
    agent: str
    risk_class: str
    safety: JobSafety
    allowed_tools: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # V4.1.1 PR2 — tool_policy.v2 intersection
    allowed_command_ids: list[str] = Field(default_factory=list)
    command_constraints: dict[str, dict] = Field(default_factory=dict)
    deny_freeform_shell: bool = True
    allow_network: bool = False
    tool_policy_status: str = "empty_missing"
    command_registry_hash: str = ""
    effective_command_policy_hash: str = ""
    command_policy_hash_algorithm: str = "sha256"
