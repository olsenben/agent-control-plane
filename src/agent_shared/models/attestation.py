"""Durable dual-attestation schemas (V4.1.1 PR3).

CT104 produces authenticated executor claims. CT103 still independently validates
patch, evidence, source binding, hashes, and publish conditions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SANDBOX_ATTESTATION_SCHEMA = "sandbox_attestation.v1"
EXECUTION_ATTESTATION_SCHEMA = "execution_attestation.v1"

TeardownStatus = Literal["destroyed", "quarantined", "unknown"]
ReadyVerdict = Literal["ready", "not_ready"]


class CapabilityTestResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class CredentialScrubReport(BaseModel):
    """Categories and names only — never secret values."""

    categories_removed: list[str] = Field(default_factory=list)
    names_removed: list[str] = Field(default_factory=list)
    token_bearing_remote_cleared: bool = False
    hooks_disabled: bool = False
    askpass_cleared: bool = False
    credential_helper_cleared: bool = False
    git_config_nosystem: bool = False
    unsafe_protocols_disabled: bool = False


class SandboxAttestationV1(BaseModel):
    """Pre-execution attestation written before model/command work starts."""

    schema_version: str = SANDBOX_ATTESTATION_SCHEMA
    run_id: str
    job_id: str = ""
    executor_id: str
    workspace_id: str
    sandbox_backend: str
    sandbox_backend_version: str = ""
    policy_source_repo: str = ""
    policy_source_sha: str = ""
    target_source_sha: str = ""
    command_registry_hash: str = ""
    effective_command_policy_hash: str = ""
    network_profile: str = "no-network"
    capability_tests: list[CapabilityTestResult] = Field(default_factory=list)
    credential_scrub: CredentialScrubReport = Field(default_factory=CredentialScrubReport)
    ct103_nonce: str = ""
    ready_verdict: ReadyVerdict = "not_ready"
    created_at: str = ""
    warnings: list[str] = Field(default_factory=list)


class ExecutionAttestationV1(BaseModel):
    """Post-teardown attestation referencing the pre-execution record."""

    schema_version: str = EXECUTION_ATTESTATION_SCHEMA
    run_id: str
    job_id: str = ""
    sandbox_attestation_id: str = ""
    sandbox_attestation_sha256: str = ""
    executor_id: str
    workspace_id: str
    patch_sha256: str = ""
    bundle_id: str = ""
    bundle_digest: str = ""
    evidence_digest: str = ""
    commands_executed: list[str] = Field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    final_target_head: str = ""
    teardown_status: TeardownStatus = "unknown"
    quarantine_location: str | None = None
    quarantine_reason: str | None = None
    executor_identity: str = ""
    ct103_nonce: str = ""
    policy_source_repo: str = ""
    policy_source_sha: str = ""
    target_base_sha: str = ""
    created_at: str = ""
    messages: list[str] = Field(default_factory=list)
