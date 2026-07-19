"""Immutable patch-bundle manifests (producer evidence only — V4.1.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PRODUCER_PROTOCOL_V1 = "patch-bundle.v1"
BUNDLE_SCHEMA_VERSION = "patch_bundle.v1"

BundleKind = Literal["fix", "repair"]


class PatchBundleManifest(BaseModel):
    """CT104-produced evidence. Authorization fields must come from CT103 state."""

    schema_version: str = BUNDLE_SCHEMA_VERSION
    bundle_id: str
    run_id: str
    attempt_id: str
    kind: BundleKind
    producer_base_sha: str
    patch_filename: str = "patch.diff"
    patch_sha256: str
    patch_size: int
    producer_tree_sha: str | None = None
    gate_snapshot_filename: str | None = None
    gate_snapshot_sha256: str | None = None
    result_filename: str | None = None
    result_sha256: str | None = None
    sandbox_attestation_filename: str | None = None
    sandbox_attestation_sha256: str | None = None
    execution_attestation_filename: str | None = None
    execution_attestation_sha256: str | None = None
    producer_protocol: str = PRODUCER_PROTOCOL_V1
    created_at: str


class AuthoritativePublishResult(BaseModel):
    """CT103-owned publish outcome — never written into bundle-inbox."""

    schema_version: str = "authoritative_publish_result.v1"
    run_id: str
    bundle_id: str
    attempt_id: str
    kind: BundleKind
    trusted_base_sha: str
    patch_sha256: str
    result_tree_sha: str
    commit_sha: str | None = None
    remote_branch: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    validation_policy_version: str | None = None
    approval_binding_id: str | None = None
    published_at: str | None = None
    publish_state: str
    messages: list[str] = Field(default_factory=list)
