"""Deterministic replay of append-only transaction events to semantic state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_control.transaction.barriers import (
    KIND_CANCELLED,
    KIND_ESCALATED,
    KIND_REJECTED,
    KIND_TIMED_OUT,
)
from agent_control.transaction.capability import (
    LIFECYCLE_CONSUMED,
    LIFECYCLE_CONSUMING,
    LIFECYCLE_EXPIRED,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_MINTED,
    lifecycle_of,
)
from agent_control.transaction.ledger import EVENT_PUBLISH_REQUESTED


@dataclass(frozen=True)
class TransactionDerivedState:
    decision: str | None
    capability_count: int
    capability_lifecycle: str | None
    publish_effect_id: str | None
    publish_state: str | None
    barrier_kinds: tuple[str, ...]
    patch_digest: str | None
    source_sha: str | None


_LIFECYCLE_RANK = {
    LIFECYCLE_MINTED: 1,
    LIFECYCLE_CONSUMING: 2,
    LIFECYCLE_CONSUMED: 3,
    LIFECYCLE_EXPIRED: 3,
    LIFECYCLE_INVALIDATED: 3,
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _payload(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    inner = _as_mapping(payload)
    nested = inner.get("payload")
    if isinstance(nested, Mapping):
        return {**inner, **dict(nested)}
    return inner if inner else dict(event)


def _event_type(event: Mapping[str, Any]) -> str:
    payload = _payload(event)
    for key in ("type", "event_type", "raw_event_type", "schema_version"):
        raw = event.get(key)
        if raw:
            return str(raw)
    for key in ("event_type", "schema_version", "type"):
        raw = payload.get(key)
        if raw:
            return str(raw)
    return ""


def _advance_lifecycle(current: str | None, incoming: str | None) -> str | None:
    if not incoming:
        return current
    if current is None:
        return incoming
    if _LIFECYCLE_RANK.get(incoming, 0) >= _LIFECYCLE_RANK.get(current, 0):
        return incoming
    return current


def replay_transaction(events: Iterable[Mapping[str, Any]]) -> TransactionDerivedState:
    """Fold append-only events into derived expected state. Deterministic; no I/O."""
    decision: str | None = None
    capability_ids: set[str] = set()
    capability_lifecycle: str | None = None
    publish_effect_id: str | None = None
    publish_state: str | None = None
    barrier_kinds: list[str] = []
    patch_digest: str | None = None
    source_sha: str | None = None

    for event in events:
        body = _as_mapping(event)
        kind = _event_type(body)
        payload = _payload(body)
        lower = kind.lower()

        if kind == "software_transaction.v1" or payload.get("schema_version") == "software_transaction.v1":
            tx = payload if payload.get("transaction_id") else body
            dec = tx.get("decision")
            if isinstance(dec, Mapping):
                decision = str(dec.get("decision") or decision)
            elif dec:
                decision = str(dec)
            patch = tx.get("patch")
            if isinstance(patch, Mapping):
                patch_digest = str(patch.get("patch_digest") or patch_digest or "") or patch_digest
                source_sha = str(patch.get("source_sha") or source_sha or "") or source_sha
            cap = tx.get("capability")
            if isinstance(cap, Mapping) and cap.get("capability_id"):
                capability_ids.add(str(cap["capability_id"]))
                capability_lifecycle = _advance_lifecycle(capability_lifecycle, LIFECYCLE_MINTED)
            outcome = str(tx.get("durable_outcome") or "")
            if outcome == "PUBLISHED":
                publish_state = "succeeded"
                capability_lifecycle = _advance_lifecycle(capability_lifecycle, LIFECYCLE_CONSUMED)
            elif outcome == "AUTO_ADMITTED_CAPABILITY_MINTED":
                capability_lifecycle = _advance_lifecycle(capability_lifecycle, LIFECYCLE_MINTED)
            elif outcome in {"ESCALATED_NO_CAPABILITY", "REJECTED_NO_CAPABILITY"}:
                publish_state = publish_state or "rejected"

        if kind in {"patch_admission_decision.v1", "admission"} or lower.endswith("admission"):
            decision = str(payload.get("decision") or body.get("decision") or decision)

        if kind in {"durable_patch_capability.v1", "capability"} or "capability" in lower:
            cap_id = payload.get("capability_id") or body.get("capability_id")
            if cap_id:
                capability_ids.add(str(cap_id))
            capability_lifecycle = _advance_lifecycle(
                capability_lifecycle, lifecycle_of(payload) if payload else lifecycle_of(body)
            )

        if (
            kind in {EVENT_PUBLISH_REQUESTED, "transaction_control_event.v1"}
            or payload.get("event_type") == EVENT_PUBLISH_REQUESTED
            or body.get("event_type") == EVENT_PUBLISH_REQUESTED
        ):
            effect = payload.get("publish_effect_id") or body.get("publish_effect_id")
            if effect:
                publish_effect_id = str(effect)
            publish_state = publish_state or "remote_pending"
            digest = payload.get("patch_digest") or body.get("patch_digest")
            if digest:
                patch_digest = str(digest)
            sha = payload.get("source_sha") or body.get("source_sha")
            if sha:
                source_sha = str(sha)

        if kind in {"publish_record.v1", "publish"} or payload.get("publish_state"):
            state = payload.get("publish_state") or body.get("publish_state")
            if state:
                publish_state = str(state)

        event_name = str(payload.get("event_type") or body.get("event_type") or kind)
        kinds_field = payload.get("kinds") or body.get("kinds")
        if isinstance(kinds_field, list):
            for item in kinds_field:
                text = str(item)
                if text and text not in barrier_kinds:
                    barrier_kinds.append(text)
        barrier_kind = payload.get("kind") or body.get("kind")
        if barrier_kind:
            text = str(barrier_kind)
            if text and text not in barrier_kinds:
                barrier_kinds.append(text)
        if event_name in {"RUN_CANCELLED", KIND_CANCELLED, "CANCELLED"} or kind == "barrier":
            if KIND_CANCELLED not in barrier_kinds:
                barrier_kinds.append(KIND_CANCELLED)
        if event_name in {"RUN_TIMED_OUT", KIND_TIMED_OUT}:
            if KIND_TIMED_OUT not in barrier_kinds:
                barrier_kinds.append(KIND_TIMED_OUT)
        if event_name in {KIND_ESCALATED, "ESCALATED"} or str(decision) == "ESCALATE":
            if KIND_ESCALATED not in barrier_kinds and event_name in {KIND_ESCALATED, "ESCALATED"}:
                barrier_kinds.append(KIND_ESCALATED)
        if event_name in {KIND_REJECTED, "REJECTED"}:
            if KIND_REJECTED not in barrier_kinds:
                barrier_kinds.append(KIND_REJECTED)

        extra_digest = payload.get("patch_digest")
        if extra_digest and not patch_digest:
            patch_digest = str(extra_digest)
        extra_sha = payload.get("source_sha")
        if extra_sha and not source_sha:
            source_sha = str(extra_sha)

    return TransactionDerivedState(
        decision=decision,
        capability_count=len(capability_ids),
        capability_lifecycle=capability_lifecycle,
        publish_effect_id=publish_effect_id,
        publish_state=publish_state,
        barrier_kinds=tuple(barrier_kinds),
        patch_digest=patch_digest,
        source_sha=source_sha,
    )
