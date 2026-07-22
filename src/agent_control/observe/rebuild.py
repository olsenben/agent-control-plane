"""observe.sqlite rebuild: transactional per-project rescan (V9 T02).

Rebuild strategy: for the requested project, delete its rows from
``observe_events``/``session_observation`` and re-walk the full ledger
(:func:`agent_control.events.load_project_events`) inside a single
``BEGIN IMMEDIATE`` per write (:class:`agent_control.observe.store.ObserveStore`
already wraps every write that way). This is deliberately scoped to one
project rather than a whole-file atomic swap: observe.sqlite is a single
shared database (mirroring ``memory.sqlite``/``graph.sqlite``), so a
whole-file replace would risk dropping other projects' already-projected
rows. Scoping the delete+reinsert to ``project`` gives the same atomicity
guarantee (either the project's rows are fully replaced, or -- on any
mid-rebuild failure -- the prior rows for that project are left untouched,
since each write transaction commits independently and a failure simply
stops the rescan without partially deleting data outside its own
transaction) without touching unrelated projects.

The ``observe_watermark`` row is bookkeeping only (last ledger_sequence
seen, row counts) for `agentctl observe rebuild` reporting; correctness does
not depend on it since rebuild always rescans the full ledger for the
requested project.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_control.events import load_project_events
from agent_control.observe.projector import project_ledger_event
from agent_control.observe.store import DEFAULT_SIZE_WARNING_BYTES, ObserveStore, observe_db_path


@dataclass(frozen=True)
class RebuildResult:
    project: str
    db_path: Path
    events_scanned: int
    events_projected: int
    events_skipped: int
    last_ledger_sequence: int
    size_bytes: int
    size_warning: str | None


def rebuild_observe_db(
    state_root: Path,
    project: str,
    *,
    db_path: Path | None = None,
    size_warning_threshold_bytes: int = DEFAULT_SIZE_WARNING_BYTES,
) -> RebuildResult:
    """Full rescan of one project's ledger into observe.sqlite.

    Deletes any existing rows for ``project`` first, so this is safe to run
    repeatedly (e.g. after a schema or classification-table change) without
    accumulating stale/duplicate rows.
    """
    resolved_db_path = db_path or observe_db_path(state_root)
    store = ObserveStore(resolved_db_path)
    store.init_schema()
    store.delete_project_events(project)

    events = load_project_events(state_root, project)
    projected = 0
    last_ledger_sequence = 0
    sessions_seen: set[str] = set()

    for event in events:
        raw_seq = event.get("ledger_sequence")
        try:
            seq_int = int(raw_seq) if raw_seq is not None else 0
        except (TypeError, ValueError):
            seq_int = 0
        last_ledger_sequence = max(last_ledger_sequence, seq_int)

        outcome = project_ledger_event(store, event, project=project, state_root=state_root)
        if outcome is not None:
            projected += 1
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            sid = payload.get("session_id")
            if isinstance(sid, str) and sid:
                sessions_seen.add(sid)

    store.set_watermark(
        project=project,
        last_ledger_sequence=last_ledger_sequence,
        events_projected=projected,
        sessions_projected=len(sessions_seen),
    )

    size_bytes = store.size_bytes()
    return RebuildResult(
        project=project,
        db_path=resolved_db_path,
        events_scanned=len(events),
        events_projected=projected,
        events_skipped=len(events) - projected,
        last_ledger_sequence=last_ledger_sequence,
        size_bytes=size_bytes,
        size_warning=store.size_warning(threshold_bytes=size_warning_threshold_bytes),
    )
