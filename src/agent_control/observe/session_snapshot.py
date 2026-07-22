"""Canonical AgentSession snapshot for session_observation (V9 T02, H6).

``session_observation`` always mirrors the *current* persisted
``AgentSession`` record (:mod:`agent_control.session.storage`), never a
reconstruction from one ledger event's payload -- whichever event triggers a
refresh, the projector re-reads the live session file, so the row converges
to the same canonical state regardless of projection order.

Per T01/H1, every stored payload goes through display-safe normalization.
``AgentSession`` is already a curated/typed record with one exception:
``terminal_reason`` is a free-text, exception-derived narrative string --
the same field the ``observe_event.v1`` classification table
(:mod:`agent_control.observe.safe_display`) marks ``redacted`` for the
equivalent ledger ``reason`` field. It is redacted here for the same reason
and never reaches the durable row.
"""

from __future__ import annotations

import json
from typing import Any

from agent_shared.models.agent_session import AgentSession

REDACTED_PLACEHOLDER = "<redacted>"


def build_session_observation_row(session: AgentSession) -> dict[str, Any]:
    """Curated, display-safe subset of ``AgentSession`` for durable projection."""
    return {
        "session_id": session.session_id,
        "project": session.project,
        "repo": session.repo,
        "run_ids_json": json.dumps(list(session.run_ids)),
        "subject_kind": session.subject_kind,
        "subject_number": session.subject_number,
        "command_kind": session.command_kind,
        "status": session.status.value,
        "trace_id": session.trace_id,
        "correlation_id": session.correlation_id,
        "risk_level": session.risk_level,
        "risk_tags_json": json.dumps(list(session.risk_tags)),
        "invoked_by": session.invoked_by,
        "acting_identity": session.acting_identity,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "finished_at": session.finished_at,
        "terminal_reason_code": session.terminal_reason_code,
        "terminal_reason_redacted": 1 if session.terminal_reason else 0,
        "session_json": json.dumps(_safe_session_dict(session)),
    }


def _safe_session_dict(session: AgentSession) -> dict[str, Any]:
    """Full session dict, minus the one free-text field (H1/T01 compliance)."""
    data = session.model_dump(mode="json")
    if data.get("terminal_reason"):
        data["terminal_reason"] = REDACTED_PLACEHOLDER
    return data
