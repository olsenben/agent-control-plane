"""Slice 5.7 — selective memory writeback from typed session trace.

Distinct from 6E.2 CI-verified fix memory (`ci.memory.writeback_fix_ci_verified`):
- 5.7 fires on successful ``session_finished`` for review/plan (hypotheses + evidence refs).
- 6E.2 fires on CT102 verdict=verified for fix (prescriptive ci_verified memory).
"""

from __future__ import annotations

import logging
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.memory.mapper import memory_record_from_completed
from agent_control.memory.store import MemoryStore
from agent_control.session.verification import load_verification_claim
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.memory import (
    ADMISSION_POLICY_VERSION_57,
    EpistemicStatus,
)
from agent_shared.models.verification_claim import VerificationClaim

logger = logging.getLogger(__name__)

_SESSION_TRACE_COMMANDS = frozenset({"review", "plan"})


def epistemic_from_claim(claim: VerificationClaim | None) -> EpistemicStatus:
    if claim is None:
        return "inferred"
    if claim.status == "passed":
        return "verified"
    if claim.status == "failed":
        return "invalidated"
    # missing / requested — structured findings remain hypotheses
    return "inferred"


def build_evidence_refs(
    session: AgentSession,
    *,
    claim: VerificationClaim | None,
    event: AgentRunCompletedEvent,
) -> list[str]:
    refs: list[str] = [f"session:{session.session_id}", f"run:{event.run_id}"]
    if session.memory_preflight and session.memory_preflight.digest:
        refs.append(f"preflight:{session.memory_preflight.digest}")
    if session.verification and session.verification.digest:
        refs.append(f"verification:{session.verification.digest}")
    elif claim is not None and claim.artifact_digest:
        refs.append(f"verification:{claim.artifact_digest}")
    if claim is not None:
        refs.append(f"verification_status:{claim.status}")
        if claim.scope_commit_sha:
            refs.append(f"scope_sha:{claim.scope_commit_sha}")
    if event.summary_hash:
        refs.append(f"summary:{event.summary_hash}")
    # stable unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def admit_session_trace_memory(
    state_root,
    session: AgentSession,
    event: AgentRunCompletedEvent,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Admit memory_record.v1 after successful session_finished (review/plan).

    Returns a compact result dict for tests / events.
    """
    settings = settings or get_settings()

    if session.status != SessionStatus.FINISHED:
        return _reject("session_not_finished", session=session)

    if session.command_kind not in _SESSION_TRACE_COMMANDS:
        return _reject("command_not_eligible", session=session)

    if event.run_id not in session.run_ids:
        return _reject("run_not_in_session", session=session)

    claim = load_verification_claim(state_root, session.project, session.session_id)
    if claim is None or session.verification is None:
        return _reject("verification_claim_required", session=session)

    if claim.session_id != session.session_id or claim.run_id != event.run_id:
        return _reject("verification_identity_mismatch", session=session)

    base = memory_record_from_completed(event)
    if base is None:
        return _reject("no_structured_result", session=session)

    epistemic = epistemic_from_claim(claim)
    evidence_refs = build_evidence_refs(session, claim=claim, event=event)
    scope = claim.scope_commit_sha or session.head_sha or None

    record = base.model_copy(
        update={
            "session_id": session.session_id,
            "epistemic_status": epistemic,
            "evidence_refs": evidence_refs,
            "verification_scope": scope,
            "admission_policy_version": ADMISSION_POLICY_VERSION_57,
            "memory_quality": "structured_result",
        }
    )

    store = MemoryStore(settings.memory_db_path)
    stored = store.upsert_record(record)
    logger.info(
        "memory_admitted session_id=%s run_id=%s record_id=%s epistemic=%s",
        session.session_id,
        event.run_id,
        stored.record_id,
        epistemic,
    )
    return {
        "admitted": True,
        "record_id": stored.record_id,
        "run_id": stored.run_id,
        "session_id": stored.session_id,
        "epistemic_status": epistemic,
        "evidence_refs": evidence_refs,
        "reason": None,
    }


def _reject(reason: str, *, session: AgentSession) -> dict[str, Any]:
    logger.info(
        "memory_rejected session_id=%s reason=%s",
        session.session_id,
        reason,
    )
    return {
        "admitted": False,
        "record_id": None,
        "run_id": None,
        "session_id": session.session_id,
        "epistemic_status": None,
        "evidence_refs": [],
        "reason": reason,
    }


def should_defer_ingest_writeback(
    state_root,
    event: AgentRunCompletedEvent,
) -> bool:
    """True when typed review/plan session will own writeback at session_finished."""
    from agent_control.session.lifecycle import (
        SessionMismatchError,
        resolve_session_for_ingest,
    )

    try:
        session = resolve_session_for_ingest(state_root, event)
    except LookupError:
        return False
    except SessionMismatchError:
        return False
    return session.command_kind in _SESSION_TRACE_COMMANDS
