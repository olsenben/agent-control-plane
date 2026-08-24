"""Cancel / timeout / escalate / reject durable barriers. Fail closed."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_shared.hash_utils import canonical_json_hash

PHASE_WORKER = "worker"
PHASE_EVIDENCE = "evidence"
PHASE_ADMISSION = "admission"
PHASE_MINT = "mint"
PHASE_PUBLISH = "publish"

KIND_CANCELLED = "CANCELLED"
KIND_TIMED_OUT = "TIMED_OUT"
KIND_ESCALATED = "ESCALATED"
KIND_REJECTED = "REJECTED"
KIND_CANCEL_TOO_LATE = "CANCEL_TOO_LATE"
KIND_CANCEL_PENDING_RECONCILIATION = "CANCEL_PENDING_RECONCILIATION"

CANCEL_TOO_LATE = "CANCEL_TOO_LATE"
CANCELLED_NO_EFFECT = "CANCELLED_NO_EFFECT"
CANCELLED_PRE_EFFECT = "CANCELLED_PRE_EFFECT"
CANCEL_PENDING_RECONCILIATION = "CANCEL_PENDING_RECONCILIATION"
AUTHORIZED_PARTIAL_EFFECT = "AUTHORIZED_PARTIAL_EFFECT"

RUN_CANCELLED = "RUN_CANCELLED"
REFUSED_CANCELLED_RUN = "REFUSED_CANCELLED_RUN"
RUN_TIMED_OUT = "RUN_TIMED_OUT"
REFUSED_TIMED_OUT_RUN = "REFUSED_TIMED_OUT_RUN"
REFUSED_ESCALATED = "REFUSED_ESCALATED"
REFUSED_REJECTED = "REFUSED_REJECTED"
REFUSED_REJECTED_REPLAY = "REFUSED_REJECTED_REPLAY"
REFUSED_LATE_EVIDENCE = "REFUSED_LATE_EVIDENCE"
REFUSED_STALE_EVENT = "REFUSED_STALE_EVENT"

_DURABLE_PHASES = frozenset(
    {PHASE_WORKER, PHASE_EVIDENCE, PHASE_ADMISSION, PHASE_MINT, PHASE_PUBLISH}
)


class DurableBarrierError(RuntimeError):
    def __init__(self, code: str, *, run_id: str, kind: str):
        self.code = code
        self.run_id = run_id
        self.kind = kind
        super().__init__(code)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def barrier_path(state_root: Path, run_id: str) -> Path:
    return Path(state_root) / "transaction" / "barriers" / f"{run_id}.json"


def load_barrier(state_root: Path, run_id: str) -> dict[str, Any] | None:
    path = barrier_path(state_root, run_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write_barrier(state_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = barrier_path(state_root, str(payload["run_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_barrier(state_root, str(payload["run_id"]))
    if existing is not None:
        # Cancel/timeout/reject/escalate are sticky. Do not resurrect.
        kinds = list(existing.get("kinds") or [])
        if payload["kind"] not in kinds:
            kinds.append(payload["kind"])
        merged = dict(existing)
        merged["kinds"] = kinds
        merged["updated_at"] = utc_now()
        if payload.get("transaction_id") and not merged.get("transaction_id"):
            merged["transaction_id"] = payload["transaction_id"]
        if payload.get("cancel_disposition"):
            merged["cancel_disposition"] = payload["cancel_disposition"]
        if payload.get("detail"):
            merged["detail"] = payload["detail"]
        body = merged
    else:
        body = dict(payload)
        body["kinds"] = [payload["kind"]]
        body["created_at"] = payload.get("timestamp") or utc_now()
        body["updated_at"] = body["created_at"]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return body


def _event(
    *,
    event_type: str,
    run_id: str,
    transaction_id: str,
    component: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "run_id": run_id,
        "transaction_id": transaction_id,
        "event_type": event_type,
        **(extra or {}),
    }
    return {
        "schema_version": "transaction_control_event.v1",
        "event_id": canonical_json_hash(
            {"event_type": event_type, "run_id": run_id, "transaction_id": transaction_id}
        )[:32],
        "transaction_id": transaction_id,
        "event_type": event_type,
        "component": component,
        "principal": None,
        "timestamp": utc_now(),
        "code_revision": None,
        "policy_revision": None,
        "payload_digest": canonical_json_hash(payload),
        "payload": payload,
        "run_id": run_id,
    }


def mark_run_cancelled(
    state_root: Path,
    *,
    run_id: str,
    transaction_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    txid = transaction_id or run_id
    record = _write_barrier(
        state_root,
        {
            "run_id": run_id,
            "transaction_id": txid,
            "project": project,
            "kind": KIND_CANCELLED,
            "timestamp": utc_now(),
        },
    )
    event = _event(
        event_type=RUN_CANCELLED,
        run_id=run_id,
        transaction_id=txid,
        component="barriers",
    )
    record["event"] = event
    return record


def cancel_transaction(
    state_root: Path,
    run_id: str,
    *,
    transaction_id: str | None = None,
    project: str | None = None,
    gitea_client: Any | None = None,
    observed: Any | None = None,
) -> dict[str, Any]:
    """Cancel a run and record point-of-no-return disposition.

    Never reports CANCELLED_NO_EFFECT when a remote effect already exists.
    """
    from agent_control.publish.state import find_intent_by_run_id
    from agent_control.transaction.reconcile import (
        ExpectedPublishEffect,
        inspect_expected_effect,
        observe_from_client,
        transaction_marker,
    )

    txid = transaction_id or run_id
    intent = find_intent_by_run_id(state_root, run_id)
    disposition = CANCELLED_PRE_EFFECT
    extra_kind = None
    detail: dict[str, Any] = {}
    observed_gitea = observed
    if intent is not None:
        disposition = CANCEL_PENDING_RECONCILIATION
        extra_kind = KIND_CANCEL_PENDING_RECONCILIATION
        expected = ExpectedPublishEffect(
            repo=intent.project,
            branch=intent.agent_branch,
            commit_sha=intent.expected_commit_sha,
            transaction_id=intent.transaction_id or txid,
            run_id=intent.run_id,
            bundle_id=intent.bundle_id,
            marker=transaction_marker(run_id=intent.run_id, bundle_id=intent.bundle_id),
        )
        if observed_gitea is None and gitea_client is not None:
            observed_gitea = observe_from_client(gitea_client, expected)
        if observed_gitea is not None:
            decision = inspect_expected_effect(expected, observed_gitea)
            if decision.already_applied or decision.status == "CONFLICT":
                disposition = CANCEL_TOO_LATE
                extra_kind = KIND_CANCEL_TOO_LATE
                detail = {"authorized_partial_effect": AUTHORIZED_PARTIAL_EFFECT}
            elif decision.status == "NOT_APPLIED":
                disposition = CANCELLED_NO_EFFECT
                extra_kind = None
    record = _write_barrier(
        state_root,
        {
            "run_id": run_id,
            "transaction_id": txid,
            "project": project,
            "kind": KIND_CANCELLED,
            "timestamp": utc_now(),
            "cancel_disposition": disposition,
            "detail": detail,
        },
    )
    if extra_kind is not None:
        record = _write_barrier(
            state_root,
            {
                "run_id": run_id,
                "transaction_id": txid,
                "project": project,
                "kind": extra_kind,
                "timestamp": utc_now(),
                "cancel_disposition": disposition,
                "detail": detail,
            },
        )
    event = _event(
        event_type=RUN_CANCELLED,
        run_id=run_id,
        transaction_id=txid,
        component="barriers",
        extra={"cancel_disposition": disposition, **detail},
    )
    record["event"] = event
    record["cancel_disposition"] = disposition
    return record


def mark_run_timed_out(
    state_root: Path,
    *,
    run_id: str,
    transaction_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    txid = transaction_id or run_id
    record = _write_barrier(
        state_root,
        {
            "run_id": run_id,
            "transaction_id": txid,
            "project": project,
            "kind": KIND_TIMED_OUT,
            "timestamp": utc_now(),
        },
    )
    event = _event(
        event_type=RUN_TIMED_OUT,
        run_id=run_id,
        transaction_id=txid,
        component="barriers",
    )
    record["event"] = event
    return record


def persist_escalate_barrier(
    state_root: Path,
    *,
    run_id: str,
    transaction_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    return _write_barrier(
        state_root,
        {
            "run_id": run_id,
            "transaction_id": transaction_id or run_id,
            "project": project,
            "kind": KIND_ESCALATED,
            "timestamp": utc_now(),
        },
    )


def refused_stale_event_dir(state_root: Path) -> Path:
    return Path(state_root) / "transaction" / "refused_stale_events"


def record_refused_stale_event(
    state_root: Path,
    *,
    event_id: str,
    transaction_id: str,
    proposal_id: str | None,
    reason: str,
    current_state: Sequence[str] | str,
    run_id: str | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    """Capture a refused late handler. Control-plane memory only; never fed into C."""
    if isinstance(current_state, str):
        kinds = [current_state]
    else:
        kinds = [str(item) for item in current_state]
    payload = {
        "schema_version": "refused_stale_event.v1",
        "event_id": str(event_id),
        "transaction_id": str(transaction_id),
        "proposal_id": proposal_id,
        "reason": str(reason),
        "current_state": kinds,
        "run_id": run_id,
        "phase": phase,
        "timestamp": utc_now(),
        "feeds_controller": False,
    }
    path = refused_stale_event_dir(state_root) / f"{_safe_id(event_id)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return payload


def _safe_id(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(value))
    return (text[:160] if text else "unknown")


def persist_reject_barrier(
    state_root: Path,
    *,
    run_id: str,
    transaction_id: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    return _write_barrier(
        state_root,
        {
            "run_id": run_id,
            "transaction_id": transaction_id or run_id,
            "project": project,
            "kind": KIND_REJECTED,
            "timestamp": utc_now(),
        },
    )


def barrier_kinds(state_root: Path, run_id: str) -> set[str]:
    record = load_barrier(state_root, run_id)
    if record is None:
        return set()
    return {str(item) for item in (record.get("kinds") or [])}


def check_durable_effect_allowed(
    state_root: Path,
    *,
    run_id: str,
    phase: Literal["worker", "evidence", "admission", "mint", "publish"],
    event_id: str | None = None,
    transaction_id: str | None = None,
    proposal_id: str | None = None,
) -> None:
    """Refuse late durable-boundary work. Distinct cancel vs timeout vs escalate vs reject."""
    if phase not in _DURABLE_PHASES:
        raise ValueError(phase)
    kinds = barrier_kinds(state_root, run_id)
    code: str | None = None
    kind: str | None = None
    if KIND_CANCELLED in kinds:
        code, kind = REFUSED_CANCELLED_RUN, KIND_CANCELLED
    elif KIND_TIMED_OUT in kinds:
        code, kind = REFUSED_TIMED_OUT_RUN, KIND_TIMED_OUT
    elif KIND_ESCALATED in kinds and phase in {PHASE_MINT, PHASE_PUBLISH}:
        code, kind = REFUSED_ESCALATED, KIND_ESCALATED
    elif KIND_REJECTED in kinds:
        kind = KIND_REJECTED
        if phase == PHASE_EVIDENCE:
            code = REFUSED_LATE_EVIDENCE
        elif phase == PHASE_MINT:
            code = REFUSED_REJECTED_REPLAY
        else:
            code = REFUSED_REJECTED
    if code is None or kind is None:
        return
    barrier = load_barrier(state_root, run_id) or {}
    txid = transaction_id or str(barrier.get("transaction_id") or run_id)
    stale_id = event_id or f"{phase}:{run_id}:{code}"
    record_refused_stale_event(
        state_root,
        event_id=stale_id,
        transaction_id=txid,
        proposal_id=proposal_id,
        reason=code,
        current_state=sorted(kinds),
        run_id=run_id,
        phase=phase,
    )
    raise DurableBarrierError(code, run_id=run_id, kind=kind)
