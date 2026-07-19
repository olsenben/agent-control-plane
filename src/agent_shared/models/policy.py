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
