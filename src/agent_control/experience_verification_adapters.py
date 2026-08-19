"""Pure adapters onto ExperienceVerificationResult (VExp W0-C).

No I/O. Does not import ``maintenance_evals``. Duck-types eval outcomes so the
control plane can map a VerificationOutcome-like object or dict without a
cross-repo runtime dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_shared.models.ci import CiVerificationResult
from agent_shared.models.experience_verification import (
    ExperienceVerificationResult,
    VerificationLane,
)
from agent_shared.models.verification_claim import VerificationClaim


def from_eval_outcome(outcome: Any) -> ExperienceVerificationResult:
    """Map a VerificationOutcome-like object or dict to the eval-harness domain.

    ``verification_scope`` is ``final`` (terminal for that scored slot).
    ``authority_domain`` is ``eval_harness``, so production finalization is false.
    """
    official_pass = bool(
        _attr(outcome, "official_pass", "official_benchmark_pass", default=False)
    )
    additional_pass = bool(
        _attr(outcome, "additional_pass", "v10_additional_verification_pass", default=False)
    )
    verified = _attr(outcome, "verified")
    verified_success = bool(verified) if verified is not None else official_pass
    claim_id = str(_attr(outcome, "claim_id", default="") or "")
    evidence_refs = [claim_id] if claim_id else []
    return ExperienceVerificationResult(
        verification_scope="final",
        authority_domain="eval_harness",
        official=VerificationLane(
            commands=_command_texts(_attr(outcome, "official_commands", default=())),
            passed=official_pass,
        ),
        additional=VerificationLane(
            commands=_command_texts(_attr(outcome, "additional_commands", default=())),
            passed=additional_pass,
        ),
        verified_success=verified_success,
        evidence_refs=evidence_refs,
    )


def from_sandbox_result(payload: Mapping[str, Any]) -> ExperienceVerificationResult:
    """Map a CT104 ``verification_result.v1`` dict to the advisory fast domain."""
    passed = bool(payload.get("passed", False))
    sandbox = payload.get("sandbox") if isinstance(payload.get("sandbox"), Mapping) else {}
    session_id = str(sandbox.get("session_id") or "") if isinstance(sandbox, Mapping) else ""
    evidence_refs = [session_id] if session_id else []
    return ExperienceVerificationResult(
        verification_scope="fast",
        authority_domain="ct104_advisory",
        official=VerificationLane(
            commands=_command_texts(payload.get("commands") or ()),
            passed=passed,
        ),
        additional=VerificationLane(commands=[], passed=False),
        verified_success=passed,
        evidence_refs=evidence_refs,
    )


def from_production_result(source: Any) -> ExperienceVerificationResult:
    """Map ``CiVerificationResult`` or ``VerificationClaim`` to CT102 production."""
    schema = str(_attr(source, "schema_version", default="") or "")
    if isinstance(source, CiVerificationResult) or schema == "ci_verification_result.v1":
        return _from_ci(source)
    if isinstance(source, VerificationClaim) or schema == "verification_claim.v1":
        return _from_claim(source)
    raise TypeError(
        "from_production_result expects CiVerificationResult or VerificationClaim"
    )


def _from_ci(source: Any) -> ExperienceVerificationResult:
    verdict = str(_attr(source, "verdict", default="") or "")
    passed = verdict == "verified"
    commands = _ci_commands(source)
    refs: list[str] = []
    for key in ("fix_run_id", "expected_head_commit_sha", "repository"):
        value = _attr(source, key, default="")
        if value:
            refs.append(str(value))
    finished_at = str(_attr(source, "evaluated_at", default="") or "") or None
    return ExperienceVerificationResult(
        verification_scope="final",
        authority_domain="ct102_production",
        official=VerificationLane(commands=commands, passed=passed),
        additional=VerificationLane(commands=[], passed=False),
        verified_success=passed,
        evidence_refs=refs,
        finished_at=finished_at,
    )


def _from_claim(source: Any) -> ExperienceVerificationResult:
    status = str(_attr(source, "status", default="") or "")
    passed = status == "passed"
    command_id = str(_attr(source, "command_id", default="") or "")
    commands = [command_id] if command_id else []
    refs: list[str] = []
    for key in ("artifact_digest", "artifact", "session_id", "run_id"):
        value = _attr(source, key, default="")
        if value:
            refs.append(str(value))
    started_at = str(_attr(source, "created_at", default="") or "") or None
    finished_at = str(_attr(source, "updated_at", default="") or "") or None
    return ExperienceVerificationResult(
        verification_scope="final",
        authority_domain="ct102_production",
        official=VerificationLane(commands=commands, passed=passed),
        additional=VerificationLane(commands=[], passed=False),
        verified_success=passed,
        evidence_refs=refs,
        started_at=started_at,
        finished_at=finished_at,
    )


def _ci_commands(source: Any) -> list[str]:
    workflows = _attr(source, "required_workflows", default=()) or ()
    commands: list[str] = []
    for item in workflows:
        if isinstance(item, str):
            if item:
                commands.append(item)
            continue
        text = (
            _attr(item, "path", default="")
            or _attr(item, "display_name", default="")
            or _attr(item, "workflow_id", default="")
        )
        if text:
            commands.append(str(text))
    return commands


def _command_texts(value: Any) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item:
                out.append(item)
            continue
        text = (
            _attr(item, "command", default="")
            or _attr(item, "command_id", default="")
            or _attr(item, "path", default="")
        )
        if text:
            out.append(str(text))
    return out


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return default
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default
