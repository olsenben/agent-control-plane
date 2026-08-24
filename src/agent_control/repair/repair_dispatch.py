"""W2 verify-repair dispatch orchestration (VExp W2-D).

Single-owner integration helpers called from ``eval_dispatch`` when
``w2_repair`` is present on the request. Production default remains off.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.authoritative_handoff import AuthoritativeHandoff
from agent_shared.models.failure_evidence import FailureEvidence
from agent_shared.models.fast_verification import (
    FastVerificationRequest,
    FastVerificationResult,
)
from agent_shared.models.fix import FixResult
from agent_shared.models.repair import (
    RepairAction,
    RepairGate,
    RepairOutcome,
    compute_repair_gate,
)

from agent_control.repair.command_selection import select_fast_verifier
from agent_control.repair.controller import FakeRepairAdapters, RepairController, RepairTaskState
from agent_control.repair.fast_verifier import run_fast_verification
from agent_control.repair.materialize import materialize
from agent_control.repair.normalize import normalize_fast_verification_result

DEFAULT_REPAIR_MODE: RepairAction = "disabled"


def parse_repair_mode(request: dict[str, Any]) -> RepairAction:
    w2 = request.get("w2_repair") or {}
    mode = str(w2.get("repair_mode") or w2.get("repair_action") or "off").lower()
    mapping = {
        "off": "disabled",
        "disabled": "disabled",
        "observe_fast_only": "observe_fast_only",
        "one_repair": "one_repair",
        "no_repair": "disabled",
    }
    return mapping.get(mode, "disabled")  # type: ignore[return-value]


def w2_repair_enabled(request: dict[str, Any]) -> bool:
    return bool(request.get("w2_repair"))


def fix_result_hash(fix: FixResult | dict[str, Any]) -> str:
    if isinstance(fix, FixResult):
        return canonical_json_hash(fix.model_dump(mode="json"))
    return canonical_json_hash(fix)


def load_fix_result(payload: dict[str, Any] | None) -> FixResult | None:
    if not payload:
        return None
    return FixResult.model_validate(payload)


def persist_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def run_fast_verify0(
    *,
    request: dict[str, Any],
    workspace: Path,
    head_sha: str,
    patch0: FixResult,
    patch0_hash: str,
    session_id: str,
    artifact_dir: Path,
    task_id: str,
) -> tuple[FastVerificationResult, FailureEvidence | None, RepairGate]:
    """Materialize exact SHA + PATCH0 and run FastVerify0 once."""
    verification = request.get("verification") or {}
    selection = select_fast_verifier(
        task={"task_id": task_id, "official_commands": verification.get("official_commands")},
        snapshot_sha=head_sha,
        verification_binding=verification,
    )
    if selection is None:
        from agent_control.repair.fast_verifier import unavailable_fast_result

        fv0 = unavailable_fast_result(
            task_id=task_id,
            session_id=session_id,
            snapshot_sha=head_sha,
            patch_hash=patch0_hash,
        )
        gate = compute_repair_gate(
            fast_result=fv0,
            failure_evidence=None,
            repair_mode=parse_repair_mode(request),
            patch0_authorized=True,
            patch0_applied=True,
        )
        return fv0, None, gate

    fv_workspace = artifact_dir / "fast_verify0_workspace"
    materialize(
        base_workspace=workspace,
        snapshot_sha=head_sha,
        fix_result=patch0,
        target=fv_workspace,
        artifact_root=artifact_dir / "fast_verify0",
    )
    fv_request = FastVerificationRequest(
        task_id=task_id,
        session_id=session_id,
        snapshot_sha=head_sha,
        patch_hash=patch0_hash,
        verifier_selection=selection,
        attempt_number=0,
    )
    fv0 = run_fast_verification(
        request=fv_request,
        workspace=fv_workspace,
        artifact_dir=artifact_dir / "fast_verify0",
    )
    evidence = normalize_fast_verification_result(
        fv0, artifact_root=artifact_dir / "fast_verify0"
    )
    gate = compute_repair_gate(
        fast_result=fv0,
        failure_evidence=evidence,
        repair_mode=parse_repair_mode(request),
        patch0_authorized=True,
        patch0_applied=True,
    )
    return fv0, evidence, gate


def load_or_validate_freeze(
    *,
    request: dict[str, Any],
    patch0: FixResult,
    patch0_hash: str,
    fv0: FastVerificationResult | None = None,
    gate: RepairGate | None = None,
) -> tuple[FastVerificationResult | None, RepairGate | None, str | None]:
    """Validate injected freeze artifacts match computed values."""
    w2 = request.get("w2_repair") or {}
    frozen = w2.get("freeze") or {}
    expected_patch0 = frozen.get("patch0_hash")
    if expected_patch0 and expected_patch0 != patch0_hash:
        return None, None, "patch0_hash_mismatch"
    if fv0 is not None:
        expected_fv0 = frozen.get("fast_verify0_hash")
        if expected_fv0 and expected_fv0 != fv0.result_hash:
            return None, None, "fast_verify0_hash_mismatch"
    if gate is not None:
        if frozen.get("repair_eligible") is not None:
            if bool(frozen["repair_eligible"]) != gate.repair_eligible:
                return None, None, "repair_eligible_mismatch"
        expected_reason = frozen.get("repair_gate_reason")
        if expected_reason and expected_reason != gate.repair_gate_reason:
            return None, None, "repair_gate_reason_mismatch"
    return fv0, gate, None


def run_w2_treatment_repair(
    *,
    request: dict[str, Any],
    workspace: Path,
    head_sha: str,
    session_id: str,
    artifact_dir: Path,
    patch0: FixResult,
    patch0_hash: str,
    fv0: FastVerificationResult,
    gate: RepairGate,
    evidence: FailureEvidence | None,
    context_pack_hash: str,
    context_pack_render: str,
    edit_policy_hash: str,
    edit_policy_statement: str,
    task_id: str,
    engine_factory: Callable[[str], Any] | None = None,
    authorize_fn: Callable[[FixResult], dict[str, Any]] | None = None,
) -> tuple[RepairOutcome, FixResult, FastVerificationResult | None]:
    """Run treatment repair path; returns outcome, final candidate fix, optional FV1."""
    repair_mode = parse_repair_mode(request)
    if repair_mode != "one_repair" or not gate.repair_eligible:
        return (
            RepairOutcome(
                repair_invoked=False,
                repair_completed=False,
                final_candidate="patch0",
                patch0_hash=patch0_hash,
                repair_gate=gate,
            ),
            patch0,
            None,
        )

    def model_gen(repair_input: str) -> FixResult | None:
        if engine_factory is None:
            return None
        import os

        # Honor EVAL_DISPATCH_ENGINE (fake in tests; official in live bakeoff).
        # Do not hardcode "official" — that bypasses the fake integration boundary.
        engine_name = (
            str(request.get("eval_dispatch_engine") or "").strip().lower()
            or (os.environ.get("EVAL_DISPATCH_ENGINE") or "official").strip().lower()
        )
        engine = engine_factory(engine_name)
        project = str(request.get("project") or "eval/project")
        job = {
            "schema_version": "rlm_job.v1",
            "run_id": f"repair-{uuid.uuid4().hex[:8]}",
            "job_id": f"job-repair-{uuid.uuid4().hex[:8]}",
            "session_id": session_id,
            "project": project,
            "flow": "eval_dispatch",
            "agent": "repair",
            "risk_class": "write_patch",
            "workflow_definition": "eval_dispatch",
            "flow_config_id": "eval_dispatch",
            "flow_version": "1",
            "command_intent": {
                "kind": "fix",
                "natural_language_task": repair_input,
            },
            "fix_authorization": {
                "allowed_files": list(patch0.files_changed),
                "approved_base_sha": head_sha,
            },
            "edit_policy": dict(request.get("edit_policy") or {}),
            "context_pack": request.get("context_pack"),
            "limits": {"max_iterations": 1},
        }
        result = engine.run(job, workspace, {"warnings": []}, artifact_dir=str(artifact_dir))
        fix = getattr(result, "fix_result", None)
        return fix if isinstance(fix, FixResult) else None

    def authorizer(fix: FixResult) -> dict[str, Any]:
        if authorize_fn:
            return authorize_fn(fix)
        return {"authorized": True, "decision": "ALLOW"}

    state = RepairTaskState(
        task_id=task_id,
        session_id=session_id,
        snapshot_sha=head_sha,
        task_text=str(request.get("problem_statement") or ""),
        context_pack_hash=context_pack_hash,
        context_pack_render=context_pack_render,
        edit_policy_hash=edit_policy_hash,
        edit_policy_statement=edit_policy_statement,
        patch0=patch0,
        patch0_hash=patch0_hash,
        patch0_authorized=True,
        patch0_applied=True,
        fast_verify0=fv0,
        failure_evidence=evidence,
        repair_gate=gate,
        repair_action="one_repair",
        workspace=workspace,
        artifact_dir=artifact_dir,
    )
    controller = RepairController()
    outcome = controller.run(
        state,
        adapters=FakeRepairAdapters(
            model_generator=model_gen,
            authorizer=authorizer,
            applier=lambda _ws, _fix: True,
        ),
    )
    final_fix = patch0
    fv1 = None
    if outcome.final_candidate == "patch1" and outcome.patch1_hash:
        repair_fix_path = artifact_dir / "fix_result_patch1.json"
        if repair_fix_path.is_file():
            final_fix = FixResult.model_validate(json.loads(repair_fix_path.read_text()))
        fv1_path = artifact_dir / "fast_verify1" / "result.json"
        if fv1_path.is_file():
            fv1 = FastVerificationResult.model_validate(json.loads(fv1_path.read_text()))
    return outcome, final_fix, fv1


def build_authoritative_handoff(
    *,
    request: dict[str, Any],
    session_id: str,
    invocation_id: str,
    head_sha: str,
    context_pack_hash: str,
    edit_policy_hash: str,
    arm: str,
    patch0_hash: str,
    fv0: FastVerificationResult,
    gate: RepairGate,
    outcome: RepairOutcome | None = None,
    evidence: FailureEvidence | None = None,
    fv1: FastVerificationResult | None = None,
    task_id: str,
) -> AuthoritativeHandoff:
    w2 = request.get("w2_repair") or {}
    repair_request_hash = None
    if outcome and outcome.repair_invoked and evidence is not None:
        from agent_shared.models.repair import RepairRequest

        repair_request_hash = RepairRequest(
            task_id=task_id,
            session_id=session_id,
            patch0_hash=patch0_hash,
            evidence_hash=evidence.evidence_hash,
            context_pack_hash=context_pack_hash,
            edit_policy_hash=edit_policy_hash,
        ).request_hash

    return AuthoritativeHandoff(
        task_id=task_id,
        session_id=session_id,
        invocation_id=invocation_id,
        snapshot_sha=head_sha,
        context_pack_hash=context_pack_hash,
        edit_policy_hash=edit_policy_hash,
        arm="control" if arm in {"control", "B1_GATED_NO_REPAIR"} else "treatment",
        repair_action=str(w2.get("repair_mode") or w2.get("repair_action") or "disabled"),
        patch0_hash=patch0_hash,
        patch0_authorized=True,
        fast_verify0_hash=fv0.result_hash,
        repair_eligible=gate.repair_eligible,
        repair_gate_reason=gate.repair_gate_reason,
        failure_evidence_hash=evidence.evidence_hash if evidence else None,
        repair_request_hash=repair_request_hash,
        patch1_hash=outcome.patch1_hash if outcome else None,
        patch1_authorized=outcome.attempt_record.authorized if outcome else None,
        fast_verify1_hash=fv1.result_hash if fv1 else None,
        final_candidate=outcome.final_candidate if outcome else "patch0",
        repair_attempts=outcome.repair_attempts if outcome else 0,
        verifier_selection_hash=fv0.verifier_selection.provenance_hash,
    )


def persist_w2_artifacts(
    artifact_dir: Path,
    *,
    patch0: FixResult,
    patch0_hash: str,
    fv0: FastVerificationResult,
    gate: RepairGate,
    evidence: FailureEvidence | None,
    handoff: AuthoritativeHandoff | None = None,
    outcome: RepairOutcome | None = None,
) -> None:
    persist_json(artifact_dir / "patch0_freeze.json", {
        "patch0_hash": patch0_hash,
        "fix_result": patch0.model_dump(mode="json"),
    })
    persist_json(artifact_dir / "fast_verify0_freeze.json", fv0)
    persist_json(artifact_dir / "repair_eligibility.json", gate)
    if evidence:
        persist_json(artifact_dir / "failure_evidence0.json", evidence)
    if handoff:
        persist_json(artifact_dir / "authoritative_handoff.json", handoff)
    if outcome:
        persist_json(artifact_dir / "repair_outcome.json", outcome)


def materialize_for_authoritative_verify(
    *,
    base_workspace: Path,
    head_sha: str,
    fix: FixResult,
    artifact_dir: Path,
) -> Path:
    """Independent materialization for authoritative dual verify."""
    target = artifact_dir / "authoritative_workspace"
    if target.exists():
        shutil.rmtree(target)
    return materialize(
        base_workspace=base_workspace,
        snapshot_sha=head_sha,
        fix_result=fix,
        target=target,
        artifact_root=artifact_dir / "authoritative",
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
