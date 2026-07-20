"""Assemble end-to-end review replay from durable CT103 artifacts.

Stages (operator console order): issue → context → model → policy → memory.
Read-only: never mutates ledger, sessions, or memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.events import load_project_events
from agent_control.memory.preflight_artifacts import (
    load_context_packet_artifact,
    load_preflight_artifact,
    session_artifact_dir,
)
from agent_control.project_identity import canonical_project
from agent_control.session.storage import load_session, load_session_by_run
from agent_control.session.verification import load_verification_claim
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.repo_identity import normalize_repo_full_name

STAGE_ORDER = ("issue", "context", "model", "policy", "memory")


class ReviewReplayError(RuntimeError):
    """Replay cannot be built from durable artifacts."""


def build_review_replay(
    state_root: Path,
    *,
    project: str,
    session_id: str | None = None,
    run_id: str | None = None,
    memory_db_path: Path | None = None,
    require_finished: bool = True,
) -> dict[str, Any]:
    """Load session + artifacts and emit a staged replay document.

    Provide ``session_id`` and/or ``run_id``. When both are set they must agree.
    """
    project = canonical_project(project)
    session = _resolve_session(
        state_root, project, session_id=session_id, run_id=run_id
    )
    if session.command_kind != "review":
        raise ReviewReplayError(
            f"session {session.session_id} is command_kind={session.command_kind!r}, "
            "expected review"
        )
    if require_finished and session.status != SessionStatus.FINISHED:
        raise ReviewReplayError(
            f"session {session.session_id} status={session.status.value}; "
            "replay smoke requires finished"
        )

    primary_run = _primary_run_id(session, run_id)
    events = _session_events(state_root, project, session)
    preflight = load_preflight_artifact(state_root, project, session.session_id)
    packet = load_context_packet_artifact(state_root, project, session.session_id)
    claim = load_verification_claim(state_root, project, session.session_id)
    memory = _load_memory_for_session(
        memory_db_path, project=project, session=session, run_id=primary_run
    )
    artifact_names = _list_session_artifacts(state_root, project, session.session_id)

    stages = {
        "issue": _stage_issue(session),
        "context": _stage_context(session, preflight, packet, claim),
        "model": _stage_model(session, events, memory),
        "policy": _stage_policy(session, events, memory),
        "memory": _stage_memory(session, events, memory),
    }
    present = {name: bool(stages[name].get("present")) for name in STAGE_ORDER}
    complete = all(present.values())

    return {
        "schema_version": "review_replay.v1",
        "project": project,
        "session_id": session.session_id,
        "run_id": primary_run,
        "command_kind": session.command_kind,
        "status": session.status.value,
        "stage_order": list(STAGE_ORDER),
        "stages": stages,
        "stages_present": present,
        "complete": complete,
        "timeline": _timeline(events),
        "artifact_files": artifact_names,
    }


def _resolve_session(
    state_root: Path,
    project: str,
    *,
    session_id: str | None,
    run_id: str | None,
) -> AgentSession:
    if not session_id and not run_id:
        raise ReviewReplayError("provide --session-id and/or --run-id")
    by_sess: AgentSession | None = None
    by_run: AgentSession | None = None
    if session_id:
        by_sess = load_session(state_root, project, session_id)
        if by_sess is None:
            raise ReviewReplayError(f"no session for {session_id}")
    if run_id:
        by_run = load_session_by_run(state_root, project, run_id)
        if by_run is None:
            raise ReviewReplayError(f"no session bound to run_id={run_id}")
    if by_sess is not None and by_run is not None:
        if by_sess.session_id != by_run.session_id:
            raise ReviewReplayError(
                f"session_id={by_sess.session_id} does not match run_id={run_id} "
                f"(bound to {by_run.session_id})"
            )
        return by_sess
    return by_sess or by_run  # type: ignore[return-value]


def _primary_run_id(session: AgentSession, run_id: str | None) -> str | None:
    if run_id:
        return run_id
    if session.run_ids:
        return session.run_ids[-1]
    return None


def _session_events(
    state_root: Path, project: str, session: AgentSession
) -> list[dict[str, Any]]:
    run_ids = set(session.run_ids)
    sid = session.session_id
    out: list[dict[str, Any]] = []
    for event in load_project_events(state_root, project):
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        ev_sid = payload.get("session_id") or event.get("session_id")
        ev_run = payload.get("run_id") or event.get("delivery_id")
        if ev_sid == sid or (isinstance(ev_run, str) and ev_run in run_ids):
            out.append(event)
    return out


def _list_session_artifacts(
    state_root: Path, project: str, session_id: str
) -> list[str]:
    root = session_artifact_dir(state_root, project, session_id)
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.endswith(".tmp"):
            names.append(path.relative_to(root).as_posix())
    return names


def _load_memory_for_session(
    memory_db_path: Path | None,
    *,
    project: str,
    session: AgentSession,
    run_id: str | None,
) -> dict[str, Any] | None:
    if memory_db_path is None:
        return None
    from agent_control.memory.store import MemoryStore

    store = MemoryStore(memory_db_path)
    record = None
    if run_id:
        record = store.get_by_run_id(run_id)
    if record is None and session.subject_kind == "issue":
        for cand in store.list_for_issue(project, session.subject_number, limit=20):
            if cand.session_id == session.session_id:
                record = cand
                break
            if run_id and cand.run_id == run_id:
                record = cand
                break
    if record is None:
        return None
    return {
        "record_id": record.record_id,
        "run_id": record.run_id,
        "session_id": record.session_id,
        "source_command": record.source_command,
        "epistemic_status": record.epistemic_status,
        "memory_quality": record.memory_quality,
        "admission_policy_version": record.admission_policy_version,
        "source_model": record.source_model,
        "source_engine": record.source_engine,
        "evidence_refs": list(record.evidence_refs),
        "findings_count": len(record.findings),
        "files_inspected": list(record.files_inspected),
        "policy_decision": record.governance.policy_decision,
        "risk_tags": list(record.governance.risk_tags),
        "created_at": record.created_at,
    }


def _stage_issue(session: AgentSession) -> dict[str, Any]:
    return {
        "present": True,
        "subject_kind": session.subject_kind,
        "subject_number": session.subject_number,
        "invoked_by": session.invoked_by,
        "acting_identity": session.acting_identity,
        "source_comment_id": session.source_comment_id,
        "correlation_id": session.correlation_id,
        "head_sha": session.head_sha,
        "input_state_sha": session.input_state_sha,
        "created_at": session.created_at,
        "finished_at": session.finished_at,
        "terminal_reason_code": session.terminal_reason_code,
    }


def _stage_context(
    session: AgentSession,
    preflight: Any,
    packet: Any,
    claim: Any,
) -> dict[str, Any]:
    present = preflight is not None or packet is not None
    body: dict[str, Any] = {
        "present": present,
        "memory_preflight_ref": (
            session.memory_preflight.model_dump(mode="json")
            if session.memory_preflight
            else None
        ),
        "context_packet_ref": (
            session.context_packet.model_dump(mode="json")
            if session.context_packet
            else None
        ),
    }
    if preflight is not None:
        body["memory_preflight"] = {
            "status": preflight.status,
            "source_sha": preflight.source_sha,
            "policy_source_sha": preflight.policy_source_sha,
            "recursive_context_required": preflight.recursive_context_required,
            "invocation_reasons": list(preflight.invocation_reasons),
            "skip_reason": preflight.skip_reason,
            "artifact_digest": preflight.artifact_digest,
            "component_results": preflight.component_results.model_dump(mode="json"),
            "prior_memory_count": preflight.heuristic_inputs.prior_memory_count,
        }
    if packet is not None:
        body["context_packet"] = {
            "source_sha": packet.source_sha,
            "policy_source_sha": packet.policy_source_sha,
            "preflight_digest": packet.preflight_digest,
            "context_pack_digest": packet.context_pack_digest,
            "artifact_digest": packet.artifact_digest,
        }
    if claim is not None:
        body["verification_claim"] = {
            "status": claim.status,
            "source": claim.source,
            "claim": claim.claim,
            "artifact_digest": claim.artifact_digest,
        }
    return body


def _stage_model(
    session: AgentSession,
    events: list[dict[str, Any]],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    model_policy = None
    engine = None
    prompt_hash = None
    prompt_hash_source = None
    summary_hash = None
    for event in events:
        if event.get("type") != "agent.run_completed":
            continue
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        model_policy = payload.get("model_policy") or model_policy
        engine = payload.get("engine") or engine
        prompt_hash = payload.get("prompt_hash") or prompt_hash
        prompt_hash_source = payload.get("prompt_hash_source") or prompt_hash_source
        summary_hash = payload.get("summary_hash") or summary_hash
    if memory:
        model_policy = model_policy or memory.get("source_model")
        engine = engine or memory.get("source_engine")
    present = bool(model_policy or engine or summary_hash or memory)
    return {
        "present": present,
        "model_policy": model_policy,
        "engine": engine,
        "prompt_hash": prompt_hash,
        "prompt_hash_source": prompt_hash_source,
        "summary_hash": summary_hash,
        "risk_level": session.risk_level,
    }


def _stage_policy(
    session: AgentSession,
    events: list[dict[str, Any]],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    policy_events: list[dict[str, Any]] = []
    for event in events:
        etype = str(event.get("type") or "")
        if etype in {
            "agent.session_blocked",
            "agent.memory_governance_denied",
            "agent.memory_preflight_failed",
            "agent.session_failed",
        } or "policy" in etype or "approval" in etype:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            policy_events.append(
                {
                    "type": etype,
                    "event_id": event.get("event_id"),
                    "recorded_at": event.get("recorded_at"),
                    "terminal_reason_code": (payload or {}).get("terminal_reason_code"),
                    "policy_decision": (payload or {}).get("policy_decision"),
                }
            )
    policy_decision = None
    if memory:
        policy_decision = memory.get("policy_decision")
    for event in events:
        if event.get("type") != "agent.run_completed":
            continue
        payload = event.get("payload") or {}
        if isinstance(payload, dict) and payload.get("policy_decision"):
            policy_decision = payload.get("policy_decision")
    present = bool(session.policy_source_sha or session.risk_level or policy_events)
    return {
        "present": present,
        "policy_source_sha": session.policy_source_sha,
        "risk_level": session.risk_level,
        "risk_tags": list(session.risk_tags),
        "policy_decision": policy_decision,
        "policy_events": policy_events,
    }


def _stage_memory(
    session: AgentSession,
    events: list[dict[str, Any]],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    memory_events = [
        {
            "type": e.get("type"),
            "event_id": e.get("event_id"),
            "recorded_at": e.get("recorded_at"),
        }
        for e in events
        if str(e.get("type") or "").startswith("agent.memory_")
    ]
    present = memory is not None or bool(memory_events)
    return {
        "present": present,
        "record": memory,
        "memory_events": memory_events,
        "subject_number": session.subject_number,
    }


def _timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        rows.append(
            {
                "recorded_at": event.get("recorded_at"),
                "type": event.get("type"),
                "event_id": event.get("event_id"),
                "run_id": (payload or {}).get("run_id"),
                "stage_hint": _stage_hint(str(event.get("type") or "")),
            }
        )
    return rows


def _stage_hint(event_type: str) -> str:
    if event_type in {"agent.session_started", "agent.subject_context_resolved"}:
        return "issue"
    if "preflight" in event_type or "context" in event_type:
        return "context"
    if event_type == "agent.run_completed" or "model" in event_type:
        return "model"
    if (
        "policy" in event_type
        or "approval" in event_type
        or event_type
        in {
            "agent.session_blocked",
            "agent.memory_governance_denied",
            "agent.session_failed",
        }
    ):
        return "policy"
    if event_type.startswith("agent.memory_"):
        return "memory"
    if event_type.startswith("agent.session_"):
        return "issue"
    return "other"


def normalize_project(project: str) -> str:
    normalized = normalize_repo_full_name(project)
    if normalized is None:
        raise ReviewReplayError(f"invalid repo: {project}")
    return normalized
