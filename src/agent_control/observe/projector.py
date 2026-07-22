"""observe.sqlite projector: fail-open secondary write after ledger append (V9 T02).

``project_event_fail_open`` is called once per successfully-appended ledger
event (:func:`agent_control.events.append_event`) as a best-effort
*secondary* write. Per hard gate H7, a projection failure must never fail
the primary ledger append: every exception raised while touching
observe.sqlite is caught and logged here, never propagated to the caller.

Only events with a resolvable ``run_id`` are projected -- this mirrors the
existing run/session-scoped timeline
(:func:`agent_control.observe.projection.build_observation_projection`);
events with no ``run_id`` (approvals keyed by issue number, etc.) are simply
out of scope for the per-run/per-session Observatory projection and are
skipped, not an error.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_control.observe.safe_display import safe_display_event
from agent_control.observe.session_snapshot import build_session_observation_row
from agent_control.observe.store import ObserveStore, observe_db_path
from agent_control.session.storage import load_session

logger = logging.getLogger(__name__)


def resolve_run_id(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    rid = payload.get("run_id") or event.get("run_id")
    return rid if isinstance(rid, str) and rid else None


def resolve_session_id(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    sid = payload.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def project_ledger_event(
    store: ObserveStore,
    event: dict[str, Any],
    *,
    project: str,
    state_root: Path,
) -> int | None:
    """Project one raw ledger event dict into observe.sqlite.

    Returns the assigned ``projection_sequence``, or ``None`` when the event
    is out of scope (no ``run_id``/``event_id``) or was already projected
    (idempotent replay). Raises ``ObserveStoreError``/``sqlite3.Error`` on a
    genuine store failure -- callers decide fail-open policy
    (:func:`project_event_fail_open`, :mod:`agent_control.cli` rebuild).
    """
    run_id = resolve_run_id(event)
    if not run_id:
        return None
    source_event_id = str(event.get("event_id") or "")
    if not source_event_id:
        return None

    session_id = resolve_session_id(event)
    source_kind = str(event.get("source") or "unknown")
    event_type = str(event.get("type") or "")

    ledger_sequence_raw = event.get("ledger_sequence")
    try:
        ledger_sequence = int(ledger_sequence_raw) if ledger_sequence_raw is not None else None
    except (TypeError, ValueError):
        ledger_sequence = None

    display = safe_display_event(event)
    sequence = store.insert_event(
        project=project,
        run_id=run_id,
        session_id=session_id,
        source_kind=source_kind,
        source_event_id=source_event_id,
        event_type=event_type,
        known_type=display.known_type,
        ledger_sequence=ledger_sequence,
        recorded_at=event.get("recorded_at"),
        observe_event_json=display.model_dump_json(),
    )
    if sequence is None:
        return None

    if session_id:
        _refresh_session_observation(
            store,
            state_root=state_root,
            project=project,
            session_id=session_id,
            projection_sequence=sequence,
        )
    return sequence


def _refresh_session_observation(
    store: ObserveStore,
    *,
    state_root: Path,
    project: str,
    session_id: str,
    projection_sequence: int,
) -> None:
    """H6: session_observation always mirrors the *current* session file."""
    session = load_session(state_root, project, session_id)
    if session is None:
        return
    row = build_session_observation_row(session)
    store.upsert_session_observation(row, projection_sequence=projection_sequence)


def project_event_fail_open(
    state_root: Path,
    event: dict[str, Any],
    *,
    project: str,
    db_path: Path | None = None,
) -> None:
    """H7 -- never let an observe.sqlite failure affect the caller.

    Cheap early-out for the common case (no run_id) avoids opening a
    connection at all for event types outside the run/session-scoped
    projection (approvals, CI matrix events, etc.).
    """
    if resolve_run_id(event) is None:
        return
    try:
        store = ObserveStore(db_path or observe_db_path(state_root))
        project_ledger_event(store, event, project=project, state_root=state_root)
    except Exception:
        logger.warning(
            "observe_sqlite_projection_failed event_id=%s type=%s project=%s",
            event.get("event_id"),
            event.get("type"),
            project,
            exc_info=True,
        )
