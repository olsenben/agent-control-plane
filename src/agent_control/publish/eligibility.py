"""CT103 publish eligibility based on dual attestations + teardown (PR3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_shared.models.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    SANDBOX_ATTESTATION_SCHEMA,
    ExecutionAttestationV1,
    SandboxAttestationV1,
)
from agent_shared.models.bundle import PatchBundleManifest


@dataclass
class PublishEligibilityResult:
    eligible: bool
    reason_codes: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    sandbox_attestation: SandboxAttestationV1 | None = None
    execution_attestation: ExecutionAttestationV1 | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
            "messages": list(self.messages),
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_publish_eligible(
    *,
    bundle_dir: Path,
    manifest: PatchBundleManifest,
    expected_nonce: str | None = None,
    require_attestations: bool = True,
) -> PublishEligibilityResult:
    """Gate CT103 publish on durable dual attestations and teardown status.

    Rules:
    - destroyed + valid dual attestations → eligible (if other checks pass elsewhere)
    - quarantined → deny (+ operator alert via reason code)
    - missing/invalid attestation → deny
    """
    reasons: list[str] = []
    messages: list[str] = []
    sandbox: SandboxAttestationV1 | None = None
    execution: ExecutionAttestationV1 | None = None

    sandbox_name = manifest.sandbox_attestation_filename or "sandbox_attestation.v1.json"
    exec_name = manifest.execution_attestation_filename or "execution_attestation.v1.json"
    sandbox_path = bundle_dir / sandbox_name
    exec_path = bundle_dir / exec_name

    if require_attestations:
        if not sandbox_path.is_file():
            reasons.append("sandbox_attestation_missing")
        else:
            try:
                sandbox = SandboxAttestationV1.model_validate(_load_json(sandbox_path))
                if sandbox.schema_version != SANDBOX_ATTESTATION_SCHEMA:
                    reasons.append("sandbox_attestation_schema_invalid")
                if sandbox.ready_verdict != "ready":
                    reasons.append("sandbox_attestation_not_ready")
                if sandbox.run_id != manifest.run_id:
                    reasons.append("sandbox_attestation_run_mismatch")
                if expected_nonce and sandbox.ct103_nonce != expected_nonce:
                    reasons.append("sandbox_attestation_nonce_mismatch")
            except (json.JSONDecodeError, ValueError) as exc:
                reasons.append("sandbox_attestation_invalid")
                messages.append(str(exc))

        if not exec_path.is_file():
            reasons.append("execution_attestation_missing")
        else:
            try:
                execution = ExecutionAttestationV1.model_validate(_load_json(exec_path))
                if execution.schema_version != EXECUTION_ATTESTATION_SCHEMA:
                    reasons.append("execution_attestation_schema_invalid")
                if execution.run_id != manifest.run_id:
                    reasons.append("execution_attestation_run_mismatch")
                if execution.bundle_id and execution.bundle_id != manifest.bundle_id:
                    reasons.append("execution_attestation_bundle_mismatch")
                if expected_nonce and execution.ct103_nonce != expected_nonce:
                    reasons.append("execution_attestation_nonce_mismatch")
                if execution.teardown_status == "quarantined":
                    reasons.append("workspace_quarantined")
                    messages.append(execution.quarantine_reason or "quarantined")
                elif execution.teardown_status != "destroyed":
                    reasons.append("teardown_not_destroyed")
                if (
                    sandbox is not None
                    and execution.sandbox_attestation_sha256
                    and sandbox_path.is_file()
                ):
                    from agent_shared.bundles.inbox import sha256_file

                    if execution.sandbox_attestation_sha256 != sha256_file(sandbox_path):
                        reasons.append("execution_attestation_sandbox_binding_mismatch")
            except (json.JSONDecodeError, ValueError) as exc:
                reasons.append("execution_attestation_invalid")
                messages.append(str(exc))

    return PublishEligibilityResult(
        eligible=not reasons,
        reason_codes=reasons,
        messages=messages,
        sandbox_attestation=sandbox,
        execution_attestation=execution,
    )
