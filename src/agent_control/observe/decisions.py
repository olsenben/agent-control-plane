"""observe_decision.v1 -- structured decision/why/evidence contract (V9 T07).

This module is the H1-style, decision-scoped safe-display choke point,
sibling to :mod:`agent_control.observe.safe_display` (which is the choke
point for the *generic* ``observe_event.v1`` stream). It never renders a
raw ``ControlDecision.metadata`` dict verbatim: only four specific,
allowlisted sub-keys (``why``, ``evidence``, ``alternatives_rejected``,
``remaining_uncertainty``) are ever read out of it, each capped and typed;
every other key -- including, defensively, anything shaped like model
chain-of-thought/internal reasoning under any name -- is dropped before it
ever reaches a view model, template, or API response. ``observe_decision.v1``
has no ``chain_of_thought`` field at all, by construction.

Why this cannot simply reuse the generic ``observe.sqlite`` projection
(T01/T02): ``agent_control.observe.safe_display`` classifies
``agent.control_decision``'s ``metadata`` field as ``metadata_only``,
which is *correct* for the generic event stream (an opaque dict must not
be assumed display-safe by default) but also means its content is
already reduced to a presence/count descriptor before it is ever written
to ``observe_events.observe_event_json``. To surface the specific,
intentionally-curated decision fields this ticket's contract requires,
this module reads the raw ledger directly
(:func:`agent_control.events.load_project_events`, the same read already
used by the pre-T02 ``build_observation_projection``) and applies its own
dedicated allowlist -- it never trusts, and never widens, the generic
``metadata_only`` classification in ``safe_display.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_control.events import load_project_events

SCHEMA_VERSION = "observe_decision.v1"

DECISION_EVENT_TYPE = "agent.control_decision"

# Defensive caps -- decision fields are curated/short by contract, not
# free-form transcripts; anything longer is truncated, never rejected
# outright (fail toward "less shown", never toward "nothing shown").
_MAX_STR_LEN = 500
_MAX_LIST_LEN = 20
_MAX_LIST_ITEM_LEN = 300

# The only metadata sub-keys this module will ever read a *value* for.
# Everything else on `metadata` -- known or unknown -- is withheld by name
# only, mirroring safe_display.py's audit-visible "prohibited_field_names"
# pattern one level down, inside this one field.
_KNOWN_METADATA_KEYS = ("why", "evidence", "alternatives_rejected", "remaining_uncertainty")

# Defense-in-depth: forces withholding even if a future producer -- or a
# maintainer mistake -- ever tries to smuggle raw model reasoning into one
# of the four known keys above (e.g. a "why" field that is actually a full
# chain-of-thought dump) or into any new key under a chain-of-thought-like
# name. This check runs on the *key name* for unknown keys, and is also
# available to callers that want to sanity-check a value's own shape.
_CHAIN_OF_THOUGHT_NAME_KEYWORDS = (
    "chain_of_thought",
    "chain-of-thought",
    "cot",
    "reasoning_trace",
    "internal_reasoning",
    "private_reasoning",
    "scratchpad",
    "raw_thoughts",
    "thinking",
)


def is_chain_of_thought_like_name(name: str) -> bool:
    """True if *name* looks like it names raw model reasoning content.

    Used to force-withhold any metadata key shaped like chain-of-thought
    content regardless of whether it happens to collide with one of the
    four known keys -- ``observe_decision.v1`` never has a
    ``chain_of_thought`` field, and this is the extra guard ensuring no
    equivalent content reaches ``why``/``remaining_uncertainty`` under a
    different name either.
    """
    lname = name.lower()
    return any(keyword in lname for keyword in _CHAIN_OF_THOUGHT_NAME_KEYWORDS)


class ObserveDecisionV1(BaseModel):
    """Display-safe rendering of one ``agent.control_decision`` ledger event.

    Never carries a raw ``metadata`` dict and has no ``chain_of_thought``
    field. ``why``/``remaining_uncertainty`` are short, capped strings;
    ``evidence``/``alternatives_rejected`` are capped lists of short
    strings. ``withheld_metadata_field_names`` retains only the *names* of
    any metadata keys this module declined to surface (audit visibility,
    matching the existing ``prohibited_field_names`` pattern elsewhere in
    the Observatory) -- never their values.
    """

    schema_version: str = SCHEMA_VERSION
    decision_id: str
    kind: str = "other"
    run_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    project: str | None = None
    recorded_at: str | None = None
    decision: str = ""
    why: str | None = None
    evidence: list[str] = Field(default_factory=list)
    alternatives_rejected: list[str] = Field(default_factory=list)
    remaining_uncertainty: str | None = None
    withheld_metadata_field_names: list[str] = Field(default_factory=list)


def _cap_str(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) > _MAX_STR_LEN:
        return value[:_MAX_STR_LEN] + "...(truncated)"
    return value


def _cap_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:_MAX_LIST_LEN]:
        if not isinstance(item, str) or not item:
            continue
        capped = item[:_MAX_LIST_ITEM_LEN]
        if len(item) > _MAX_LIST_ITEM_LEN:
            capped += "...(truncated)"
        out.append(capped)
    return out


def sanitize_decision_metadata(metadata: Any) -> tuple[dict[str, Any], list[str]]:
    """Extract only the known-safe ``observe_decision.v1`` sub-fields.

    Default-deny, allowlist-only, scoped to exactly the four keys in
    ``_KNOWN_METADATA_KEYS``. Every other key on *metadata* -- including a
    known key whose *name* also looks chain-of-thought-shaped (defense in
    depth against a mislabeled key) -- is withheld and returned by name
    only in the second tuple element; its value is never read into the
    first.
    """
    if not isinstance(metadata, dict):
        return {}, []
    extracted: dict[str, Any] = {}
    withheld: list[str] = []
    for name, value in metadata.items():
        if not isinstance(name, str):
            continue
        if name not in _KNOWN_METADATA_KEYS or is_chain_of_thought_like_name(name):
            withheld.append(name)
            continue
        if name in ("why", "remaining_uncertainty"):
            capped = _cap_str(value)
            if capped is not None:
                extracted[name] = capped
        elif name in ("evidence", "alternatives_rejected"):
            extracted[name] = _cap_list_of_str(value)
    return extracted, sorted(withheld)


def build_decision_from_raw_event(event: dict[str, Any]) -> ObserveDecisionV1 | None:
    """Build one ``observe_decision.v1`` record from a raw ``agent.control_decision``
    ledger event dict (envelope + ``payload``, as produced by
    :func:`agent_control.events.load_project_events`).

    Returns ``None`` for anything that is not a well-formed decision event
    (wrong type, missing payload, missing ``decision_id``) -- callers skip
    it, never render a partial/guessed record.
    """
    if event.get("type") != DECISION_EVENT_TYPE:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    decision_id = payload.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id:
        return None

    kind = payload.get("kind")
    summary = payload.get("summary")
    evidence_refs = payload.get("evidence_refs")
    metadata_fields, withheld = sanitize_decision_metadata(payload.get("metadata"))

    evidence = _cap_list_of_str(evidence_refs)
    for item in metadata_fields.get("evidence", []):
        if item not in evidence and len(evidence) < _MAX_LIST_LEN:
            evidence.append(item)

    def _opt_str(field_name: str) -> str | None:
        value = payload.get(field_name)
        return value if isinstance(value, str) and value else None

    return ObserveDecisionV1(
        decision_id=decision_id,
        kind=kind if isinstance(kind, str) and kind else "other",
        run_id=_opt_str("run_id"),
        session_id=_opt_str("session_id"),
        trace_id=_opt_str("trace_id"),
        project=event.get("project") if isinstance(event.get("project"), str) else None,
        recorded_at=event.get("recorded_at") if isinstance(event.get("recorded_at"), str) else None,
        decision=_cap_str(summary) or "",
        why=metadata_fields.get("why"),
        evidence=evidence,
        alternatives_rejected=metadata_fields.get("alternatives_rejected", []),
        remaining_uncertainty=metadata_fields.get("remaining_uncertainty"),
        withheld_metadata_field_names=withheld,
    )


def _matches_run_or_session(payload: dict[str, Any], *, run_id: str | None, session_id: str | None) -> bool:
    if run_id and payload.get("run_id") == run_id:
        return True
    if session_id and payload.get("session_id") == session_id:
        return True
    return False


def list_decisions_for_run(
    state_root: Path,
    *,
    project: str,
    run_id: str | None = None,
    session_id: str | None = None,
) -> list[ObserveDecisionV1]:
    """All ``agent.control_decision`` events for one run/session, oldest first.

    Reads the raw per-project ledger directly and applies this module's own
    decision-scoped sanitizer to each matching event -- never depends on,
    and never widens, the generic ``observe.sqlite`` projection's
    ``metadata_only`` handling of the same event type (see module
    docstring). When neither ``run_id`` nor ``session_id`` is given,
    returns an empty list rather than every decision in the project.
    """
    if not run_id and not session_id:
        return []
    events = load_project_events(state_root, project)
    decisions: list[ObserveDecisionV1] = []
    for event in events:
        if event.get("type") != DECISION_EVENT_TYPE:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if not _matches_run_or_session(payload, run_id=run_id, session_id=session_id):
            continue
        decision = build_decision_from_raw_event(event)
        if decision is not None:
            decisions.append(decision)
    return decisions


DECISIONS_PANEL_LIMIT = 50


def decisions_panel_view(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    limit: int = DECISIONS_PANEL_LIMIT,
) -> dict[str, Any]:
    """Panel 3 view-model: ``observe_decision.v1`` records for this run, oldest first.

    A plain dict of primitives/lists/dicts (mirrors the shape of
    :mod:`agent_control.observe.ui`'s other panel builders) so the template
    layer never needs to know about the Pydantic model directly. Bounded to
    the most recent *limit* decisions (homelab-scale panel, matching the
    other bounded panels in this UI) -- ``total`` always reflects the true
    count for this run, independent of the cap.
    """
    decisions = list_decisions_for_run(state_root, project=project, run_id=run_id)
    total = len(decisions)
    limited = decisions[-limit:] if limit > 0 else decisions
    return {
        "decisions": [d.model_dump(mode="json") for d in limited],
        "total": total,
    }
