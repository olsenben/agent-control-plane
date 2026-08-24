"""Deterministic repair orchestration (VExp W2-C).

No LLM decides whether repair is needed; gate is pure function of frozen inputs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.failure_evidence import FailureEvidence
from agent_shared.models.fast_verification import (
    FastVerificationRequest,
    FastVerificationResult,
)
from agent_shared.models.fix import FixResult
from agent_shared.models.repair import (
    FinalCandidate,
    RepairAction,
    RepairAttemptRecord,
    RepairBudget,
    RepairGate,
    RepairOutcome,
    RepairRequest,
    compute_repair_gate,
)

from agent_control.repair.fast_verifier import run_fast_verification
from agent_control.repair.repair_input import build_repair_context, build_repair_input


@dataclass
class RepairTaskState:
    """Frozen inputs for one repair orchestration fork."""

    task_id: str
    session_id: str
    snapshot_sha: str
    task_text: str
    context_pack_hash: str
    context_pack_render: str
    edit_policy_hash: str
    edit_policy_statement: str
    patch0: FixResult
    patch0_hash: str
    patch0_authorized: bool = True
    patch0_applied: bool = True
    fast_verify0: FastVerificationResult | None = None
    failure_evidence: FailureEvidence | None = None
    repair_gate: RepairGate | None = None
    repair_action: RepairAction = "one_repair"
    workspace: Path | None = None
    artifact_dir: Path | None = None
    allowed_files: list[str] = field(default_factory=list)


ModelGenerator = Callable[[str], FixResult | None]
PatchAuthorizer = Callable[[FixResult], dict[str, Any]]
PatchApplier = Callable[[Path, FixResult], bool]


@dataclass
class FakeRepairAdapters:
    """Test doubles for model, authorization, and apply."""

    model_generator: ModelGenerator | None = None
    authorizer: PatchAuthorizer | None = None
    applier: PatchApplier | None = None
    fast_verifier_runner: Callable[..., FastVerificationResult] | None = None


class RepairController:
    """Bounded one-repair orchestrator."""

    def __init__(self, *, budget: RepairBudget | None = None) -> None:
        self.budget = budget or RepairBudget.default()

    def run(
        self,
        state: RepairTaskState,
        *,
        adapters: FakeRepairAdapters | None = None,
    ) -> RepairOutcome:
        gate = state.repair_gate or compute_repair_gate(
            fast_result=state.fast_verify0,  # type: ignore[arg-type]
            failure_evidence=state.failure_evidence,
            budget=self.budget,
            patch0_authorized=state.patch0_authorized,
            patch0_applied=state.patch0_applied,
            repair_mode=state.repair_action,
        )

        if state.repair_action in {"disabled", "observe_fast_only"}:
            return RepairOutcome(
                repair_invoked=False,
                repair_completed=False,
                repair_attempts=0,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                repair_gate=gate,
            )

        if not gate.repair_eligible:
            return RepairOutcome(
                repair_invoked=False,
                repair_completed=False,
                repair_attempts=0,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                repair_gate=gate,
            )

        if self.budget.remaining_repair_attempts <= 0:
            return RepairOutcome(
                repair_invoked=True,
                repair_completed=False,
                repair_attempts=0,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                repair_gate=gate,
            )

        evidence = state.failure_evidence
        if evidence is None:
            # Eligible gate without evidence is a wiring defect; do not silently
            # skip the spent-or-not accounting path for observe/disabled modes.
            return RepairOutcome(
                repair_invoked=False,
                repair_completed=False,
                repair_attempts=0,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                repair_gate=gate,
            )

        context = build_repair_context(
            task_id=state.task_id,
            session_id=state.session_id,
            snapshot_sha=state.snapshot_sha,
            patch0_hash=state.patch0_hash,
            context_pack_hash=state.context_pack_hash,
            edit_policy_hash=state.edit_policy_hash,
            failure_evidence=evidence,
        )
        repair_input = build_repair_input(
            task_text=state.task_text,
            context_pack_render=state.context_pack_render,
            edit_policy_statement=state.edit_policy_statement,
            patch0=state.patch0,
            failure_evidence=evidence,
            repair_context=context,
        )

        repair_request = RepairRequest(
            task_id=state.task_id,
            session_id=state.session_id,
            patch0_hash=state.patch0_hash,
            evidence_hash=evidence.evidence_hash,
            context_pack_hash=state.context_pack_hash,
            edit_policy_hash=state.edit_policy_hash,
        )
        if state.artifact_dir is not None:
            req_path = state.artifact_dir / "repair_request.json"
            req_path.parent.mkdir(parents=True, exist_ok=True)
            req_path.write_text(
                json.dumps(repair_request.model_dump(mode="json"), indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

        # Spend the repair action at model-dispatch time (not after PATCH1 success).
        attempt = RepairAttemptRecord(
            attempt_number=1,
            repair_invoked=True,
        )
        patch1: FixResult | None = None
        repair_model_succeeded = False
        try:
            if adapters and adapters.model_generator:
                patch1 = adapters.model_generator(repair_input)
                repair_model_succeeded = patch1 is not None
            else:
                patch1 = None
        except Exception as exc:
            attempt.parse_success = False
            if state.artifact_dir is not None:
                fail_path = state.artifact_dir / "repair_model_failure.json"
                fail_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "repair_model_failure.v1",
                            "repair_invoked": True,
                            "repair_attempts": 1,
                            "repair_model_succeeded": False,
                            "repair_request_hash": repair_request.request_hash,
                            "reason": "model_dispatch_exception",
                            "error": str(exc)[:2000],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return RepairOutcome(
                repair_invoked=True,
                repair_completed=False,
                repair_attempts=1,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                attempt_record=attempt,
                repair_gate=gate,
            )

        if not repair_model_succeeded or patch1 is None:
            attempt.parse_success = False
            if state.artifact_dir is not None:
                fail_path = state.artifact_dir / "repair_model_failure.json"
                fail_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "repair_model_failure.v1",
                            "repair_invoked": True,
                            "repair_attempts": 1,
                            "repair_model_succeeded": False,
                            "repair_request_hash": repair_request.request_hash,
                            "reason": "model_returned_no_fix_result",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return RepairOutcome(
                repair_invoked=True,
                repair_completed=False,
                repair_attempts=1,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                attempt_record=attempt,
                repair_gate=gate,
            )

        attempt.parse_success = True
        patch1_hash = canonical_json_hash(patch1.model_dump(mode="json"))
        if state.artifact_dir is not None:
            patch1_path = state.artifact_dir / "fix_result_patch1.json"
            patch1_path.write_text(
                json.dumps(patch1.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        auth: dict[str, Any]
        if adapters and adapters.authorizer:
            auth = adapters.authorizer(patch1)
        else:
            auth = {"authorized": True, "decision": "ALLOW"}

        authorized = bool(auth.get("authorized") or auth.get("decision") == "ALLOW")
        attempt.authorized = authorized
        if not authorized:
            attempt.policy_rejected = True
            return RepairOutcome(
                repair_invoked=True,
                repair_completed=False,
                repair_attempts=1,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                patch1_hash=patch1_hash,
                attempt_record=attempt,
                repair_gate=gate,
            )

        applied = True
        if state.workspace is not None:
            if adapters and adapters.applier:
                applied = adapters.applier(state.workspace, patch1)
            elif state.artifact_dir is not None:
                from agent_control.repair.materialize import materialize

                try:
                    target = state.artifact_dir / "patch1_workspace"
                    materialize(
                        base_workspace=state.workspace,
                        snapshot_sha=state.snapshot_sha,
                        fix_result=patch1,
                        target=target,
                        allowed_files=state.allowed_files or None,
                        artifact_root=state.artifact_dir / "patch1_materialize",
                    )
                except Exception:
                    applied = False
        attempt.applied = applied
        if not applied:
            return RepairOutcome(
                repair_invoked=True,
                repair_completed=False,
                repair_attempts=1,
                final_candidate="patch0",
                patch0_hash=state.patch0_hash,
                patch1_hash=patch1_hash,
                attempt_record=attempt,
                repair_gate=gate,
            )

        fast1: FastVerificationResult | None = None
        if state.fast_verify0 and (adapters and adapters.fast_verifier_runner):
            fv_request = FastVerificationRequest(
                task_id=state.task_id,
                session_id=state.session_id,
                snapshot_sha=state.snapshot_sha,
                patch_hash=patch1_hash,
                verifier_selection=state.fast_verify0.verifier_selection,
                attempt_number=1,
            )
            fast1 = adapters.fast_verifier_runner(fv_request)
            attempt.fast_verify_status = fast1.status
        elif (
            state.workspace is not None
            and state.artifact_dir is not None
            and state.fast_verify0
        ):
            fv_request = FastVerificationRequest(
                task_id=state.task_id,
                session_id=state.session_id,
                snapshot_sha=state.snapshot_sha,
                patch_hash=patch1_hash,
                verifier_selection=state.fast_verify0.verifier_selection,
                attempt_number=1,
            )
            target = state.artifact_dir / "patch1_workspace"
            fast1 = run_fast_verification(
                request=fv_request,
                workspace=target,
                artifact_dir=state.artifact_dir / "fast_verify1",
            )
            attempt.fast_verify_status = fast1.status

        attempt.final_candidate = "patch1"
        attempt.patch1_hash = patch1_hash
        return RepairOutcome(
            repair_invoked=True,
            repair_completed=True,
            repair_attempts=1,
            final_candidate="patch1",
            patch0_hash=state.patch0_hash,
            patch1_hash=patch1_hash,
            attempt_record=attempt,
            repair_gate=gate,
        )

    def select_final_candidate(self, outcome: RepairOutcome) -> FinalCandidate:
        return outcome.final_candidate
