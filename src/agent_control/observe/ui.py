"""Jinja2 + HTMX five-panel Observatory session-detail UI (V9 T04).

This module only assembles already display-safe view-model dicts for the
templates under ``templates/`` -- it never introduces a second raw-payload
path. Every value that reaches a template came from one of:

- :mod:`agent_control.observe.session_snapshot` / ``session_observation``
  (V9 T02, H6: canonical, redacted mirror of ``AgentSession``) for panel 1.
- ``observe.sqlite``'s ``observe_events.observe_event_json`` (V9 T01/T02
  ``safe_display_event`` output) for panels 2 and 4 -- the same store T03's
  protected SSE stream already treats as the sole system of record.
- ``AgentSession``'s ``SessionArtifactRef`` fields (digest/size/path/schema
  name only, never artifact content) for panel 5.

Templates additionally auto-escape every value (``Jinja2Templates`` selects
autoescape for ``.html`` templates) and the :func:`display_value` filter
below never returns a ``Markup``/"safe" value -- hostile HTML, ANSI escape
sequences, or Markdown in any stored string render as inert text, never as
markup, color codes, or script.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

from agent_control.observe.session_snapshot import build_session_observation_row
from agent_control.observe.store import ObserveStore
from agent_shared.models.agent_session import AgentSession

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

TIMELINE_PAGE_SIZE = 25
LIVE_LOG_SIZE = 20

# Artifact ref attribute names on AgentSession that carry a SessionArtifactRef
# (agent_shared.models.memory_preflight.SessionArtifactRef) -- digest/path/
# size/schema-name only, never artifact content. Mirrors the set already
# read by the JSON artifacts endpoint (observe_session_artifacts).
ARTIFACT_REF_ATTRS: tuple[str, ...] = (
    "memory_preflight",
    "context_packet",
    "recursive_context",
    "verification",
)


def display_value(value: Any) -> str:
    """Render an already display-safe value as plain text.

    Only ever normalizes *shape* (dict/list -> compact JSON text); never
    marks anything ``safe``/HTML, so the surrounding Jinja auto-escaping
    still applies to whatever this returns. A hostile string (HTML tag,
    ANSI escape sequence, Markdown) that made it this far as a plain
    ``str`` round-trips through here unchanged and is escaped by the
    template exactly like any other text node.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _build_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["display_value"] = display_value
    return templates


templates = _build_templates()


def _load_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def current_state_view(
    session: AgentSession,
    store: ObserveStore,
    *,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Panel 1: current state, sourced from ``session_observation`` (H6).

    ``session_observation`` is T02's canonical, redacted mirror of the
    session record this store was last told about. When no event has been
    projected for this session yet (a brand-new, just-queued session), fall
    back to the same curated/redacted builder the projector itself uses
    (:func:`build_session_observation_row`) so the two code paths can never
    disagree about which fields are display-safe.

    ``ci_phase`` (V9 T08) is additive and optional -- only populated when
    *state_root* is given -- and is read directly from the canonical
    verification lifecycle (:func:`agent_control.observe.ci_channel.current_ci_phase_view`),
    never re-derived from raw CI event replay order (see that function's
    docstring for why a late/duplicate CI verdict cannot regress it).
    """
    row = store.get_session_observation(session.session_id)
    if row is None:
        row = build_session_observation_row(session)
    view = {
        "session_id": row.get("session_id"),
        "project": row.get("project"),
        "repo": row.get("repo"),
        "command_kind": row.get("command_kind"),
        "status": row.get("status"),
        "trace_id": row.get("trace_id"),
        "correlation_id": row.get("correlation_id"),
        "risk_level": row.get("risk_level"),
        "risk_tags": _load_json_list(row.get("risk_tags_json")),
        "invoked_by": row.get("invoked_by"),
        "acting_identity": row.get("acting_identity"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "finished_at": row.get("finished_at"),
        "terminal_reason_code": row.get("terminal_reason_code"),
        "terminal_reason_redacted": bool(row.get("terminal_reason_redacted")),
        "run_ids": _load_json_list(row.get("run_ids_json")),
        "ci_phase": None,
    }
    if state_root is not None:
        from agent_control.observe.ci_channel import current_ci_phase_view

        project = row.get("project") or session.project
        view["ci_phase"] = current_ci_phase_view(
            state_root, project=project, session_id=session.session_id
        )
    return view


def _parse_event_row(row: dict[str, Any]) -> dict[str, Any]:
    """One ``observe_events`` row -> a display-only dict for the templates.

    ``observe_event_json`` is already the display-safe ``observe_event.v1``
    payload (T01 ``safe_display_event`` / T02 projector); this only
    reshapes the already-safe fields for rendering. It never reaches into
    any other, non-display-safe field of the row.
    """
    try:
        event = json.loads(row["observe_event_json"])
    except (TypeError, ValueError):
        event = {}
    if not isinstance(event, dict):
        event = {}
    return {
        "sequence": int(row["projection_sequence"]),
        "type": event.get("type") or row.get("event_type") or "",
        "known_type": bool(event.get("known_type")),
        # V9 T08: optional Observatory log-category tag (for example "ci"
        # for the CT102 fix_ci_*/verification_* channel); None for every
        # event type outside that channel.
        "category": event.get("category"),
        "summary": event.get("summary") or "",
        "recorded_at": row.get("recorded_at"),
        "display_fields": event.get("display_fields") or {},
        "metadata_only_field_names": event.get("metadata_only_field_names") or [],
        "redacted_field_names": event.get("redacted_field_names") or [],
        "prohibited_field_names": event.get("prohibited_field_names") or [],
    }


def timeline_page_view(
    store: ObserveStore,
    run_id: str,
    *,
    after_sequence: int = 0,
    limit: int = TIMELINE_PAGE_SIZE,
) -> dict[str, Any]:
    """Panel 2: decision timeline, keyset-paginated over ``observe.sqlite``.

    Pagination is plain-link forward-only over the durable, per-run
    ``projection_sequence`` (H3) -- no JavaScript is required to move to
    the next page, since it is just a query-string ``after_sequence`` on a
    normal ``<a href>``.
    """
    after_sequence = max(0, after_sequence)
    limit = max(1, limit)
    rows = store.list_events_for_run(run_id, after_sequence=after_sequence, limit=limit)
    total = store.count_events_for_run(run_id)
    events = [_parse_event_row(r) for r in rows]
    next_after_sequence = events[-1]["sequence"] if events else after_sequence
    has_more = next_after_sequence < total
    return {
        "events": events,
        "after_sequence": after_sequence,
        "next_after_sequence": next_after_sequence,
        "has_more": has_more,
        "total": total,
        "limit": limit,
    }


def live_log_view(store: ObserveStore, run_id: str, *, limit: int = LIVE_LOG_SIZE) -> dict[str, Any]:
    """Panel 4 (baseline / HTMX-poll-fallback) data: the latest *limit* events.

    Rendered both on the initial full-page load and by the HTMX poll
    fragment endpoint (:mod:`agent_control.observe.routes`,
    ``observe_session_live_fragment``) -- one view builder, one template
    partial, so a browser with JavaScript disabled (which never fires the
    HTMX poll or the progressive-enhancement ``EventSource`` script) still
    sees this same safe-display snapshot from the initial page load.
    """
    limit = max(1, limit)
    total = store.count_events_for_run(run_id)
    after = max(0, total - limit)
    rows = store.list_events_for_run(run_id, after_sequence=after, limit=limit)
    events = [_parse_event_row(r) for r in rows]
    events.reverse()  # newest first for a "live tail" reading order
    return {"events": events, "total": total}


def artifacts_view(session: AgentSession) -> dict[str, Any]:
    """Panel 5: metadata-only artifact index (T07 owns real dispositions).

    Every field below comes from ``SessionArtifactRef``
    (:mod:`agent_shared.models.memory_preflight`) -- a digest, a byte size,
    a canonical relative path under the artifact root, a schema name, and a
    timestamp. Never the artifact's own content. ``disposition`` is fixed
    to ``metadata_only`` for all rows until T07 introduces
    ``redacted_text_view`` / ``downloadable_redacted_copy``.
    """
    refs: list[dict[str, Any]] = []
    for name in ARTIFACT_REF_ATTRS:
        ref = getattr(session, name, None)
        if ref is None:
            continue
        refs.append(
            {
                "kind": name,
                "artifact_type": ref.artifact_type,
                "disposition": "metadata_only",
                "digest": ref.digest,
                "byte_size": ref.byte_size,
                "schema_name": ref.schema_name,
                "relative_path": ref.relative_path,
                "created_at": ref.created_at,
            }
        )
    return {"artifacts": refs}
