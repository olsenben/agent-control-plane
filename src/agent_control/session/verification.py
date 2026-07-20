"""Session verification evidence gate (Slice 5.6).

CT103-only: machine-recorded claims. Fix/repair stay running after publish until
a 6E CI terminal verdict (or expire → verification_missing).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.memory.preflight_artifacts import session_artifact_dir
from agent_control.project_identity import canonical_project
from agent_control.session.events import (
    append_verification_failed,
    append_verification_missing,
    append_verification_passed,
    append_verification_requested,
)
from agent_control.session.reasons import SessionTerminalReason
from agent_control.session.storage import load_session_by_run, save_session
from agent_shared.models.agent_session import AgentSession, TERMINAL_STATUSES
from agent_shared.models.memory_preflight import SessionArtifactRef
from agent_shared.models.verification_claim import (
    VerificationClaim,
    VerificationSource,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

_CLAIM_FILENAME = "verification_claim.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim_path(state_root: Path, project: str, session_id: str) -> Path:
    return session_artifact_dir(state_root, project, session_id) / _CLAIM_FILENAME


def _relative_to_state(state_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(state_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest_claim_payload(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body["artifact_digest"] = ""
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def persist_verification_claim(
    state_root: Path,
    claim: VerificationClaim,
) -> tuple[VerificationClaim, SessionArtifactRef, bool]:
    """Persist verification_claim.json. Same digest → reuse; status updates overwrite."""
    path = _claim_path(state_root, claim.repo, claim.session_id)
    body = claim.model_dump(mode="json")
    digest = digest_claim_payload(body)
    stamped = claim.model_copy(update={"artifact_digest": digest})
    raw = json.dumps(stamped.model_dump(mode="json"), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )

    created = True
    if path.is_file():
        existing_raw = path.read_bytes()
        try:
            existing = VerificationClaim.model_validate(
                json.loads(existing_raw.decode("utf-8"))
            )
        except (json.JSONDecodeError, ValueError):
            existing = None
        if existing is not None and existing.artifact_digest == digest:
            ref = SessionArtifactRef(
                artifact_type="verification_claim",
                relative_path=_relative_to_state(state_root, path),
                digest=existing.artifact_digest or digest,
                byte_size=len(existing_raw),
                schema_name=existing.schema_version,
                created_at=existing.created_at,
            )
            return existing, ref, False
        created = False

    _atomic_write_bytes(path, raw)
    ref = SessionArtifactRef(
        artifact_type="verification_claim",
        relative_path=_relative_to_state(state_root, path),
        digest=digest,
        byte_size=len(raw),
        schema_name=stamped.schema_version,
        created_at=stamped.created_at,
    )
    return stamped, ref, created


def load_verification_claim(
    state_root: Path, project: str, session_id: str
) -> VerificationClaim | None:
    path = _claim_path(state_root, canonical_project(project), session_id)
    if not path.is_file():
        return None
    try:
        return VerificationClaim.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def format_verification_markdown(claim: VerificationClaim) -> str:
    """V4 section 0.5 Verification block for Gitea comments."""
    lines = [
        "Verification:",
        f"- claim: {claim.claim}",
        f"  scope: commit `{claim.scope_commit_sha}`",
        f"  command: {claim.command_id or '(none)'}",
        f"  source: {claim.source}",
        f"  status: {claim.status}",
        f"  artifact: {claim.artifact or '(none)'}",
        f"  limitations: {claim.limitations or '(none)'}",
    ]
    return "\n".join(lines)


def _attach_ref(session: AgentSession, ref: SessionArtifactRef) -> AgentSession:
    return session.model_copy(update={"verification": ref, "updated_at": _now()})


def request_session_verification(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    commit_sha: str,
    source: VerificationSource = "ct102",
    command_id: str | None = ".gitea/workflows/ci.yaml",
    limitations: str | None = None,
) -> AgentSession | None:
    """After successful publish: emit verification_requested; keep session running."""
    session = load_session_by_run(state_root, project, run_id)
    if session is None:
        logger.warning("verification_request_no_session run_id=%s", run_id)
        return None
    if session.command_kind not in ("fix", "repair"):
        return session
    if session.status in TERMINAL_STATUSES:
        logger.info(
            "verification_request_skip_terminal session_id=%s status=%s",
            session.session_id,
            session.status.value,
        )
        return session

    from agent_control.session.lifecycle import mark_session_running

    session = mark_session_running(state_root, session)
    now = _now()
    existing = load_verification_claim(state_root, session.project, session.session_id)
    if (
        existing is not None
        and existing.status == "requested"
        and existing.scope_commit_sha == commit_sha
        and existing.run_id == run_id
    ):
        return session

    claim = VerificationClaim(
        session_id=session.session_id,
        run_id=run_id,
        repo=session.project,
        claim="CT102 required workflows for published agent commit",
        scope_commit_sha=commit_sha,
        source=source,
        status="requested",
        command_id=command_id,
        artifact="",
        limitations=limitations
        or "Publish succeeded; CI not yet terminal. Not fixed_verified.",
        created_at=existing.created_at if existing else now,
        updated_at=now,
        risk_tags=list(session.risk_tags),
    )
    stamped, ref, _ = persist_verification_claim(state_root, claim)
    session = _attach_ref(session, ref)
    save_session(state_root, session)
    append_verification_requested(
        state_root,
        session,
        run_id=run_id,
        claim=stamped,
    )
    return session


def emit_ingest_verification_missing(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
) -> AgentSession:
    """Review/plan: explicit verification_missing before session_finished."""
    now = _now()
    claim = VerificationClaim(
        session_id=session.session_id,
        run_id=run_id,
        repo=session.project,
        claim=f"no CT102/ACI verification applied for /agent {session.command_kind}",
        scope_commit_sha=session.head_sha,
        source="none",
        status="missing",
        command_id=None,
        artifact="",
        limitations=(
            f"{session.command_kind} findings/plans are hypotheses; "
            "no machine CI or ACI command evidence was required or recorded."
        ),
        created_at=now,
        updated_at=now,
        risk_tags=list(session.risk_tags),
    )
    stamped, ref, _ = persist_verification_claim(state_root, claim)
    session = _attach_ref(session, ref)
    save_session(state_root, session)
    append_verification_missing(
        state_root,
        session,
        run_id=run_id,
        claim=stamped,
    )
    return session


def apply_ci_verdict_to_session(
    state_root: Path,
    *,
    project: str,
    fix_run_id: str,
    verdict: str,
    previous_verdict: str,
    expected_head_commit_sha: str,
    verdict_revision: int,
    artifact: str = "",
    defer_fail_for_repair: bool = False,
) -> AgentSession | None:
    """Map 6E terminal verdict to verification event + optional session finalize."""
    if verdict == "superseded":
        return None
    if verdict not in ("verified", "failing", "expired"):
        return None
    if verdict == previous_verdict:
        # Still allow idempotent re-entry when claim already matches.
        pass

    session = load_session_by_run(state_root, project, fix_run_id)
    if session is None:
        logger.info("verification_verdict_no_session run_id=%s", fix_run_id)
        return None
    if session.command_kind not in ("fix", "repair"):
        return session
    if session.status in TERMINAL_STATUSES:
        return session

    existing = load_verification_claim(state_root, session.project, session.session_id)
    now = _now()
    status: VerificationStatus
    source: VerificationSource = "ct102"
    claim_text: str
    limitations: str
    if verdict == "verified":
        status = "passed"
        claim_text = "CT102 required workflows passed for published agent commit"
        limitations = (
            "Scoped to checks actually run on this exact commit; "
            "not universal correctness."
        )
    elif verdict == "failing":
        status = "failed"
        claim_text = "CT102 required workflows failed for published agent commit"
        limitations = (
            "One or more required workflows failed. "
            + (
                "Session remains open for automatic repair."
                if defer_fail_for_repair
                else "No further automatic repair in this observe cycle."
            )
        )
    else:
        status = "missing"
        source = "none"
        claim_text = "required CT102 verification evidence expired or never arrived"
        limitations = "Pending CI expired without a verified/failing terminal verdict."

    if (
        existing is not None
        and existing.status == status
        and existing.scope_commit_sha == expected_head_commit_sha
        and existing.verdict_revision == verdict_revision
    ):
        return session

    claim = VerificationClaim(
        session_id=session.session_id,
        run_id=fix_run_id,
        repo=session.project,
        claim=claim_text,
        scope_commit_sha=expected_head_commit_sha,
        source=source,
        status=status,
        command_id=".gitea/workflows/ci.yaml",
        artifact=artifact or f"fix_run_id={fix_run_id}:rev{verdict_revision}",
        limitations=limitations,
        verdict_revision=verdict_revision,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        risk_tags=list(session.risk_tags),
    )
    stamped, ref, _ = persist_verification_claim(state_root, claim)
    session = _attach_ref(session, ref)
    save_session(state_root, session)

    from agent_control.session.lifecycle import finalize_session

    if status == "passed":
        append_verification_passed(state_root, session, run_id=fix_run_id, claim=stamped)
        reason = (
            SessionTerminalReason.REPAIR_CI_VERIFIED
            if session.command_kind == "repair"
            else SessionTerminalReason.CI_VERIFIED
        )
        return finalize_session(
            state_root,
            session,
            run_id=fix_run_id,
            status="finished",
            reason_code=reason,
            reason="CT102 CI verified for published commit",
        )

    if status == "failed":
        append_verification_failed(state_root, session, run_id=fix_run_id, claim=stamped)
        if defer_fail_for_repair:
            return session
        return finalize_session(
            state_root,
            session,
            run_id=fix_run_id,
            status="failed",
            reason_code=SessionTerminalReason.VERIFICATION_FAILED,
            reason="CT102 CI failing for published commit",
        )

    append_verification_missing(state_root, session, run_id=fix_run_id, claim=stamped)
    return finalize_session(
        state_root,
        session,
        run_id=fix_run_id,
        status="blocked",
        reason_code=SessionTerminalReason.VERIFICATION_MISSING,
        reason="required verification evidence missing or expired",
    )
