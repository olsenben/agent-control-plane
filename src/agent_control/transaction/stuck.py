"""Stuck-transaction detector. Surfaces STUCK_TRANSACTION; never auto-completes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from agent_shared.hash_utils import canonical_json_hash

StuckState = Literal[
    "PATCH_PROPOSED",
    "EVIDENCE_PENDING",
    "ESCALATED",
    "CAPABILITY_MINTED",
    "PUBLISH_REQUESTED",
    "VERIFICATION_PENDING",
]

STUCK_STATES: tuple[StuckState, ...] = (
    "PATCH_PROPOSED",
    "EVIDENCE_PENDING",
    "ESCALATED",
    "CAPABILITY_MINTED",
    "PUBLISH_REQUESTED",
    "VERIFICATION_PENDING",
)

STUCK_TRANSACTION = "STUCK_TRANSACTION"

DEFAULT_SLA_SECONDS: dict[str, int] = {
    "PATCH_PROPOSED": 900,
    "EVIDENCE_PENDING": 900,
    "ESCALATED": 3600,
    "CAPABILITY_MINTED": 900,
    "PUBLISH_REQUESTED": 600,
    "VERIFICATION_PENDING": 1800,
}


@dataclass(frozen=True)
class StuckCandidate:
    transaction_id: str
    state: StuckState
    updated_at: str
    run_id: str | None = None
    repository: str | None = None


@dataclass(frozen=True)
class StuckAlert:
    transaction_id: str
    state: StuckState
    age_seconds: float
    sla_seconds: int
    code: str = STUCK_TRANSACTION
    auto_completed: bool = False
    event: dict[str, Any] | None = None


def _parse_ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def detect_stuck_transactions(
    candidates: Iterable[StuckCandidate],
    *,
    now: datetime | None = None,
    sla_seconds: dict[str, int] | None = None,
) -> list[StuckAlert]:
    """Age/SLA detector. Does not force completion or mutate transaction outcome."""
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    thresholds = {**DEFAULT_SLA_SECONDS, **(sla_seconds or {})}
    alerts: list[StuckAlert] = []
    for candidate in candidates:
        sla = int(thresholds.get(candidate.state, DEFAULT_SLA_SECONDS[candidate.state]))
        age = (clock - _parse_ts(candidate.updated_at)).total_seconds()
        if age < sla:
            continue
        payload = {
            "transaction_id": candidate.transaction_id,
            "state": candidate.state,
            "age_seconds": age,
            "sla_seconds": sla,
            "run_id": candidate.run_id,
            "repository": candidate.repository,
            "auto_completed": False,
        }
        event = {
            "schema_version": "transaction_control_event.v1",
            "event_id": canonical_json_hash(
                {
                    "event_type": STUCK_TRANSACTION,
                    "transaction_id": candidate.transaction_id,
                    "state": candidate.state,
                }
            )[:32],
            "transaction_id": candidate.transaction_id,
            "event_type": STUCK_TRANSACTION,
            "component": "stuck_detector",
            "principal": None,
            "timestamp": clock.isoformat(),
            "code_revision": None,
            "policy_revision": None,
            "payload_digest": canonical_json_hash(payload),
            "payload": payload,
            "run_id": candidate.run_id,
            "repository": candidate.repository,
        }
        alerts.append(
            StuckAlert(
                transaction_id=candidate.transaction_id,
                state=candidate.state,
                age_seconds=age,
                sla_seconds=sla,
                code=STUCK_TRANSACTION,
                auto_completed=False,
                event=event,
            )
        )
    return alerts
