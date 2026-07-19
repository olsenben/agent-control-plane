"""Executor workspace lifecycle + dual attestation (V4.1.1 PR3).

Sequence:
  allocated → workspace_prepared → sandbox_attested → work_started
  → bundle_finalized → workspace_destroyed|quarantined
  → execution_attestation_finalized
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_control.aci.backends.base import SandboxAttestation
from agent_control.aci.backends.probes import host_identity, run_canary_probes
from agent_shared.bundles.inbox import BundleError, sha256_file, write_ready_bundle
from agent_shared.git_hygiene import scrub_clone_credentials
from agent_shared.models.attestation import (
    CapabilityTestResult,
    CredentialScrubReport,
    ExecutionAttestationV1,
    SandboxAttestationV1,
)
from agent_shared.models.bundle import BundleKind, PatchBundleManifest

LifecycleState = Literal[
    "allocated",
    "workspace_prepared",
    "sandbox_attested",
    "work_started",
    "bundle_finalized",
    "workspace_destroyed",
    "workspace_quarantined",
    "execution_attestation_finalized",
]

SANDBOX_ATTESTATION_FILENAME = "sandbox_attestation.v1.json"
EXECUTION_ATTESTATION_FILENAME = "execution_attestation.v1.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def default_executor_id() -> str:
    return f"ct104:{platform.node()}"


def default_workspace_id(run_id: str) -> str:
    return f"ws-{run_id}"


def issue_ct103_nonce() -> str:
    """CT103-issued anti-replay nonce bound into attestations."""
    return uuid.uuid4().hex


def resolve_runtime_attestation(
    workspace: Path,
    *,
    backend_name: str | None = None,
    policy_hash: str = "",
    allow_simulation: bool = False,
) -> SandboxAttestation:
    """Attest workspace; optionally fall back to SimulationSandboxBackend.

    Simulation is for fake model_policy / unit tests only — never a production
    substitute when strong isolation is required and unavailable.
    """
    from agent_control.aci.backends.srt import get_sandbox_backend
    from agent_control.config import get_settings

    name = backend_name
    if not name:
        try:
            name = get_settings().sandbox_backend
        except Exception:
            name = "srt"
    backend = get_sandbox_backend(name or "srt", expected_policy_hash=policy_hash or None)
    attestation = backend.attest(workspace=workspace, policy_hash=policy_hash)
    if attestation.strong_ok:
        return attestation
    if allow_simulation:
        sim = get_sandbox_backend("simulation")
        return sim.attest(workspace=workspace, policy_hash=policy_hash or "simulated")
    return attestation


class ExecutorLifecycle:
    """Owns workspace attest → work → durable bundle → teardown → exec attest."""

    def __init__(
        self,
        *,
        run_id: str,
        job_id: str = "",
        executor_id: str | None = None,
        workspace_id: str | None = None,
        ct103_nonce: str = "",
        policy_source_repo: str = "",
        policy_source_sha: str = "",
        target_source_sha: str = "",
        command_registry_hash: str = "",
        effective_command_policy_hash: str = "",
        network_profile: str = "no-network",
        durable_root: Path | None = None,
        quarantine_root: Path | None = None,
    ) -> None:
        self.run_id = run_id
        self.job_id = job_id
        self.executor_id = executor_id or default_executor_id()
        self.workspace_id = workspace_id or default_workspace_id(run_id)
        self.ct103_nonce = ct103_nonce
        self.policy_source_repo = policy_source_repo
        self.policy_source_sha = policy_source_sha
        self.target_source_sha = target_source_sha
        self.command_registry_hash = command_registry_hash
        self.effective_command_policy_hash = effective_command_policy_hash
        self.network_profile = network_profile
        self.durable_root = durable_root
        self.quarantine_root = quarantine_root
        self.state: LifecycleState = "allocated"
        self.workspace: Path | None = None
        self.scrub: CredentialScrubReport = CredentialScrubReport()
        self.sandbox_attestation: SandboxAttestationV1 | None = None
        self.execution_attestation: ExecutionAttestationV1 | None = None
        self.runtime_attestation: SandboxAttestation | None = None
        self.commands_executed: list[str] = []
        self.started_at: str = ""
        self.ended_at: str = ""
        self.bundle_manifest: PatchBundleManifest | None = None
        self.bundle_dir: Path | None = None
        self.teardown_status: Literal["destroyed", "quarantined", "unknown"] = "unknown"
        self.quarantine_location: str | None = None
        self.quarantine_reason: str | None = None
        self.final_target_head: str = ""
        self.patch_sha256: str = ""
        self.evidence_digest: str = ""
        self.messages: list[str] = []

    def mark_workspace_prepared(
        self,
        workspace: Path,
        *,
        token_free_remote: str | None = None,
        scrub: bool = True,
    ) -> CredentialScrubReport:
        self.workspace = workspace
        if scrub:
            self.scrub = scrub_clone_credentials(workspace, token_free_remote=token_free_remote)
        self.state = "workspace_prepared"
        return self.scrub

    def write_sandbox_attestation(
        self,
        artifact_dir: Path,
        *,
        runtime_attestation: SandboxAttestation | None = None,
        capability_tests: list[CapabilityTestResult] | None = None,
    ) -> SandboxAttestationV1:
        """Pre-execution durable attestation. Fail closed if not ready."""
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_attestation = runtime_attestation
        tests = capability_tests
        if tests is None:
            if runtime_attestation is not None and runtime_attestation.probes:
                tests = [
                    CapabilityTestResult(name=p.name, passed=p.passed, detail=p.detail)
                    for p in runtime_attestation.probes
                ]
            elif self.workspace is not None:
                probes = run_canary_probes(self.workspace)
                tests = [
                    CapabilityTestResult(name=p.name, passed=p.passed, detail=p.detail)
                    for p in probes
                ]
        tests = tests or []
        strong_ok = bool(runtime_attestation and runtime_attestation.strong_ok)
        caps_ok = all(t.passed for t in tests) if tests else strong_ok
        ready: Literal["ready", "not_ready"] = "ready" if strong_ok and caps_ok else "not_ready"
        warnings: list[str] = []
        if not strong_ok:
            warnings.append("runtime_attestation_not_strong")
        if tests and not caps_ok:
            warnings.append("capability_tests_failed")
        if not self.ct103_nonce:
            warnings.append("missing_ct103_nonce")
            ready = "not_ready"

        attest = SandboxAttestationV1(
            run_id=self.run_id,
            job_id=self.job_id,
            executor_id=self.executor_id,
            workspace_id=self.workspace_id,
            sandbox_backend=(runtime_attestation.backend if runtime_attestation else "unknown"),
            sandbox_backend_version=(
                runtime_attestation.backend_version if runtime_attestation else ""
            ),
            policy_source_repo=self.policy_source_repo,
            policy_source_sha=self.policy_source_sha,
            target_source_sha=self.target_source_sha,
            command_registry_hash=self.command_registry_hash,
            effective_command_policy_hash=self.effective_command_policy_hash,
            network_profile=self.network_profile,
            capability_tests=tests,
            credential_scrub=self.scrub,
            ct103_nonce=self.ct103_nonce,
            ready_verdict=ready,
            created_at=_now(),
            warnings=warnings,
        )
        path = artifact_dir / SANDBOX_ATTESTATION_FILENAME
        path.write_text(attest.model_dump_json(indent=2), encoding="utf-8")
        self.sandbox_attestation = attest
        self.state = "sandbox_attested"
        if ready != "ready":
            raise RuntimeError(f"sandbox_attestation_not_ready:{','.join(warnings)}")
        return attest

    def mark_work_started(self) -> None:
        self.started_at = _now()
        self.state = "work_started"

    def record_command(self, command_id: str) -> None:
        self.commands_executed.append(command_id)

    def finalize_durable_bundle(
        self,
        state_root: Path,
        *,
        kind: BundleKind,
        attempt_id: str,
        producer_base_sha: str,
        patch_bytes: bytes,
        producer_tree_sha: str | None = None,
        gate_snapshot: dict[str, Any] | bytes | None = None,
        result_payload: dict[str, Any] | bytes | None = None,
        evidence_payload: dict[str, Any] | bytes | None = None,
        publication_log: dict[str, Any] | bytes | None = None,
        artifact_dir: Path | None = None,
    ) -> PatchBundleManifest:
        """Write durable READY bundle including preflight attestation — before teardown."""
        if self.sandbox_attestation is None:
            raise BundleError("sandbox_attestation_required_before_bundle")
        if self.sandbox_attestation.ready_verdict != "ready":
            raise BundleError("sandbox_attestation_not_ready")

        extra: dict[str, bytes] = {}
        sandbox_bytes = self.sandbox_attestation.model_dump_json(indent=2).encode("utf-8")
        extra[SANDBOX_ATTESTATION_FILENAME] = sandbox_bytes

        if evidence_payload is not None:
            if isinstance(evidence_payload, bytes):
                evidence_bytes = evidence_payload
            else:
                evidence_bytes = json.dumps(evidence_payload, indent=2, sort_keys=True).encode("utf-8")
            extra["evidence.json"] = evidence_bytes
            self.evidence_digest = _sha256_bytes(evidence_bytes)
        if publication_log is not None:
            if isinstance(publication_log, bytes):
                pub_bytes = publication_log
            else:
                pub_bytes = json.dumps(publication_log, indent=2, sort_keys=True).encode("utf-8")
            extra["publication_log.json"] = pub_bytes

        # Also keep a run-local copy under artifact_dir when provided
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / SANDBOX_ATTESTATION_FILENAME).write_bytes(sandbox_bytes)

        manifest = write_ready_bundle(
            state_root,
            run_id=self.run_id,
            kind=kind,
            attempt_id=attempt_id,
            producer_base_sha=producer_base_sha,
            patch_bytes=patch_bytes,
            producer_tree_sha=producer_tree_sha,
            gate_snapshot=gate_snapshot,
            result_payload=result_payload,
            extra_artifacts=extra,
        )
        self.bundle_manifest = manifest
        self.patch_sha256 = manifest.patch_sha256
        from agent_shared.bundles.inbox import bundle_dir

        self.bundle_dir = bundle_dir(
            state_root,
            run_id=self.run_id,
            kind=kind,
            attempt_id=manifest.attempt_id,
            bundle_id=manifest.bundle_id,
        )
        self.state = "bundle_finalized"
        return manifest

    def teardown_workspace(self) -> Literal["destroyed", "quarantined"]:
        """Destroy workspace after durable bundle; quarantine on failure."""
        ws = self.workspace
        if ws is None or not ws.exists():
            self.teardown_status = "destroyed"
            self.state = "workspace_destroyed"
            return "destroyed"

        try:
            shutil.rmtree(ws)
            if ws.exists():
                raise RuntimeError("workspace_still_present")
            self.teardown_status = "destroyed"
            self.state = "workspace_destroyed"
            return "destroyed"
        except Exception as exc:
            reason = str(exc) or "teardown_failed"
            self.quarantine_reason = reason
            qroot = self.quarantine_root
            if qroot is None and self.durable_root is not None:
                qroot = self.durable_root / "quarantine"
            if qroot is None:
                qroot = ws.parent / "quarantine"
            qroot.mkdir(parents=True, exist_ok=True)
            dest = qroot / f"{self.run_id}-{self.workspace_id}"
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            try:
                shutil.move(str(ws), str(dest))
                self.quarantine_location = str(dest)
            except Exception:
                self.quarantine_location = str(ws)
            self.teardown_status = "quarantined"
            self.state = "workspace_quarantined"
            self.messages.append(f"executor_quarantined:{reason}")
            return "quarantined"

    def write_execution_attestation(
        self,
        *,
        artifact_dir: Path | None = None,
        final_target_head: str = "",
        executor_identity: str | None = None,
    ) -> ExecutionAttestationV1:
        """Post-teardown attestation; attach into durable bundle when possible."""
        self.ended_at = _now()
        self.final_target_head = final_target_head or self.final_target_head
        sandbox = self.sandbox_attestation
        sandbox_id = ""
        sandbox_sha = ""
        if sandbox is not None:
            # Hash must match on-disk serialization (indent=2) used by eligibility
            sandbox_bytes = sandbox.model_dump_json(indent=2).encode("utf-8")
            sandbox_sha = _sha256_bytes(sandbox_bytes)
            sandbox_id = f"{sandbox.run_id}:{sandbox.created_at}"

        bundle_digest = ""
        if self.bundle_manifest is not None:
            bundle_digest = _sha256_text(self.bundle_manifest.model_dump_json())

        attest = ExecutionAttestationV1(
            run_id=self.run_id,
            job_id=self.job_id,
            sandbox_attestation_id=sandbox_id,
            sandbox_attestation_sha256=sandbox_sha,
            executor_id=self.executor_id,
            workspace_id=self.workspace_id,
            patch_sha256=self.patch_sha256,
            bundle_id=self.bundle_manifest.bundle_id if self.bundle_manifest else "",
            bundle_digest=bundle_digest,
            evidence_digest=self.evidence_digest,
            commands_executed=list(self.commands_executed),
            started_at=self.started_at,
            ended_at=self.ended_at,
            final_target_head=self.final_target_head,
            teardown_status=self.teardown_status,
            quarantine_location=self.quarantine_location,
            quarantine_reason=self.quarantine_reason,
            executor_identity=executor_identity or host_identity(),
            ct103_nonce=self.ct103_nonce,
            policy_source_repo=self.policy_source_repo,
            policy_source_sha=self.policy_source_sha,
            target_base_sha=self.target_source_sha,
            created_at=_now(),
            messages=list(self.messages),
        )
        self.execution_attestation = attest

        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / EXECUTION_ATTESTATION_FILENAME).write_text(
                attest.model_dump_json(indent=2),
                encoding="utf-8",
            )

        if self.bundle_dir is not None and self.bundle_dir.is_dir():
            dest = self.bundle_dir / EXECUTION_ATTESTATION_FILENAME
            dest.write_text(attest.model_dump_json(indent=2), encoding="utf-8")
            # Update manifest digests if present
            man_path = self.bundle_dir / "manifest.json"
            if man_path.is_file():
                try:
                    data = json.loads(man_path.read_text(encoding="utf-8"))
                    data["execution_attestation_filename"] = EXECUTION_ATTESTATION_FILENAME
                    data["execution_attestation_sha256"] = sha256_file(dest)
                    if self.sandbox_attestation is not None:
                        data["sandbox_attestation_filename"] = SANDBOX_ATTESTATION_FILENAME
                        sap = self.bundle_dir / SANDBOX_ATTESTATION_FILENAME
                        if sap.is_file():
                            data["sandbox_attestation_sha256"] = sha256_file(sap)
                    man_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
                except (json.JSONDecodeError, OSError) as exc:
                    self.messages.append(f"manifest_attest_update_failed:{exc}")

        self.state = "execution_attestation_finalized"
        return attest
