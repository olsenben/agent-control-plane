"""CT102 CI channel into the Agent Observatory (V9 T08).

T02's generic projector (:mod:`agent_control.observe.projector`) only
projects events with a resolvable ``run_id`` -- for most event families that
is ``payload.run_id``. The CT102 CI truth-loop event family
(``agent.fix_ci_*``, :mod:`agent_control.ci.events` /
:mod:`agent_shared.models.ci`) instead keys everything by ``fix_run_id``,
which *is* the underlying fix/repair session's ``run_id``
(:func:`agent_control.session.verification.apply_ci_verdict_to_session`
already resolves it the same way via
:func:`agent_control.session.storage.load_session_by_run`). This module is
the single place that teaches the rest of the Observatory pipeline how to
read that event family, without changing the generic projector's contract
for every other event type:

- :data:`FIX_CI_EVENT_TYPES` / :data:`CI_CHANNEL_EVENT_TYPES` -- the event
  ``type`` strings this channel owns (used for run_id/session_id
  resolution, in :func:`agent_control.observe.safe_display.safe_display_event`
  for the "CI" log category, and by tests).
- :func:`resolve_ci_run_id` / :func:`resolve_ci_session_id` -- additive
  fallbacks the projector calls only when the generic
  ``payload.run_id`` / ``payload.session_id`` lookup comes up empty.
- :func:`flatten_observation_fields` -- ``agent.fix_ci_observed`` carries a
  nested ``WorkflowObservation`` object; safe-display classification
  operates on top-level payload keys only (H1's default-deny table), so
  this flattens its known-safe scalar fields to top-level ``observation_*``
  keys *before* classification. The nested blob itself stays out of the
  classification table and is therefore withheld (name-only) like any
  other unlisted field -- never a second, unreviewed path to display data.
- :func:`build_ci_deep_link` -- H1-adjacent trust boundary: a CT102 Actions
  run URL built *only* from ``Settings.gitea_base_url`` (server config) and
  the trusted, structured ``repository`` / ``workflow_run_id`` fields this
  codebase itself records (never the webhook's own free-form ``html_url``,
  which this module never even reads).
- :func:`current_ci_phase_view` -- current-state "phase" for the
  Observatory's panel 1, read directly from the *canonical* verification
  artifact (:mod:`agent_control.session.verification`'s
  ``verification_claim.json``) -- never re-derived from raw CI event replay
  order. Because that claim is itself only ever written while the session
  is non-terminal (``apply_ci_verdict_to_session`` returns early once
  ``session.status in TERMINAL_STATUSES``), a late or duplicate CI verdict
  can never regress this phase once the session has gone terminal: there is
  nothing to regress *from* other than the one current canonical record.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agent_control.config import Settings, get_settings

logger = logging.getLogger(__name__)

# --- event type scope ---

FIX_CI_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent.fix_ci_observed",
        "agent.fix_ci_verdict_changed",
        "agent.fix_ci_failure_evidence_collected",
        "agent.fix_ci_failure_evidence_unavailable",
        "agent.fix_ci_repair_requested",
        "agent.fix_ci_repair_blocked",
        "agent.fix_ci_repair_started",
        "agent.fix_ci_repair_pushed",
        "agent.fix_ci_repair_exhausted",
        "agent.fix_ci_repair_stale",
    }
)

VERIFICATION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent.verification_requested",
        "agent.verification_passed",
        "agent.verification_failed",
        "agent.verification_missing",
    }
)

# "CT102 CI channel" for the Observatory timeline: the fix_ci_* truth-loop
# events plus the verification_* events they ultimately drive
# (agent.verification_* already carry payload.run_id/session_id via
# agent_shared.models.agent_session.SessionEventCorrelation and are already
# projected by the generic path -- they are included here only so the "CI"
# log category / summary grouping covers the whole CT102 CI story, not so
# the projector needs a new run_id/session_id path for them).
CI_CHANNEL_EVENT_TYPES: frozenset[str] = FIX_CI_EVENT_TYPES | VERIFICATION_EVENT_TYPES

CI_LOG_CATEGORY = "ci"


def ci_log_category(event_type: str) -> str | None:
    """Observatory timeline/log category for *event_type*, or ``None``."""
    return CI_LOG_CATEGORY if event_type in CI_CHANNEL_EVENT_TYPES else None


# --- run_id / session_id resolution (additive fallback for the projector) ---


def resolve_ci_run_id(event: dict[str, Any]) -> str | None:
    """``fix_run_id`` -> ``run_id`` for the fix_ci_* channel only.

    Returns ``None`` for every other event type -- callers must still try
    the generic ``payload.run_id`` lookup first; this is a fallback, not a
    replacement.
    """
    event_type = str(event.get("type") or "")
    if event_type not in FIX_CI_EVENT_TYPES:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    rid = payload.get("fix_run_id")
    return rid if isinstance(rid, str) and rid else None


def resolve_ci_session_id(state_root: Path, project: str, run_id: str) -> str | None:
    """Best-effort session lookup for a fix_ci_* event keyed by ``fix_run_id``.

    fix_ci_* ledger events never carry ``session_id`` in their payload --
    only the underlying fix/repair session's ``run_id``
    (``fix_run_id``). A lookup failure (session pruned, or a race with
    session creation) is not an error: the event is still projected, just
    without a ``session_id``, the same as any other run-scoped event whose
    session cannot be resolved today.
    """
    try:
        from agent_control.session.storage import load_session_by_run

        session = load_session_by_run(state_root, project, run_id)
    except Exception:
        logger.warning(
            "ci_channel_session_lookup_failed run_id=%s project=%s",
            run_id,
            project,
            exc_info=True,
        )
        return None
    return session.session_id if session is not None else None


# --- nested WorkflowObservation flatten (H1: classification is top-level-key-only) ---

_OBSERVATION_SCALAR_FIELDS: tuple[str, ...] = (
    "workflow_id",
    "path",
    "display_name",
    "workflow_run_id",
    "run_attempt",
    "status",
    "conclusion",
    "head_sha",
    "pr_number",
    "api_verification_status",
    "observed_at",
)


def flatten_observation_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Flatten ``payload.observation.*`` to top-level ``observation_*`` keys.

    Only applies to ``agent.fix_ci_observed`` (the one fix_ci_* event that
    carries a nested :class:`agent_shared.models.ci.WorkflowObservation`).
    Every other event is returned unchanged (same object, not copied) so
    this is a cheap no-op for the common case. Never mutates the input
    dict -- returns a shallow copy with a new ``payload`` when it applies.
    """
    if event.get("type") != "agent.fix_ci_observed":
        return event
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return event
    observation = payload.get("observation")
    if not isinstance(observation, dict):
        return event

    flattened_payload = dict(payload)
    for key in _OBSERVATION_SCALAR_FIELDS:
        if key in observation:
            flattened_payload[f"observation_{key}"] = observation[key]

    flattened_event = dict(event)
    flattened_event["payload"] = flattened_payload
    return flattened_event


# --- CI deep links: trusted structured fields only ---

# Matches every `repository` this codebase produces
# (agent_shared.repo_identity.split_repo_full_name's own "owner/repo"
# convention) while rejecting anything that could break out of a URL path
# segment (whitespace, extra "/", "..", query/fragment characters).
_REPOSITORY_SAFE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Gitea Actions workflow_run ids are numeric in practice; also accept a
# short alnum/underscore/hyphen token so a defensive-but-not-brittle check
# does not need to change if that ever carries a synthetic id in tests.
_WORKFLOW_RUN_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_safe_repository_slug(value: Any) -> bool:
    return isinstance(value, str) and bool(_REPOSITORY_SAFE_RE.match(value))


def is_safe_workflow_run_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_WORKFLOW_RUN_ID_SAFE_RE.match(value))


def build_ci_deep_link(
    *,
    repository: Any,
    workflow_run_id: Any,
    settings: Settings | None = None,
) -> str | None:
    """CT102 Actions run URL, or ``None`` if it must be omitted.

    Built *only* from ``Settings.gitea_base_url`` (server-side config) and
    the two trusted, structured fields this codebase itself records for
    every fix_ci_* observation (``repository`` from the CT103 pending-CI
    record, ``workflow_run_id`` from the API-confirmed observation --
    :func:`agent_control.ci.observe._confirm_via_api` prefers the Gitea API
    response over the raw webhook when they differ). Never reads or
    interpolates the webhook's own free-form ``html_url``/``event`` fields
    (:func:`agent_control.ci.observe.extract_workflow_run_fields`) -- those
    are not structured/trusted for this purpose. Fails closed (returns
    ``None``) on an unset/malformed base URL or either field failing its
    conservative allowlist, mirroring
    :mod:`agent_control.observe_links`'s ``OBSERVE_PUBLIC_BASE_URL`` pattern
    (H8) for this codebase's other externally-reachable link surface.
    """
    settings = settings or get_settings()
    base = (settings.gitea_base_url or "").strip()
    if not base or not (base.startswith("http://") or base.startswith("https://")):
        return None
    if not is_safe_repository_slug(repository) or not is_safe_workflow_run_id(workflow_run_id):
        logger.warning(
            "ci_deep_link_unsafe_fields repository=%r workflow_run_id=%r",
            repository,
            workflow_run_id,
        )
        return None
    owner, _, repo = repository.partition("/")
    return (
        f"{base.rstrip('/')}/{quote(owner, safe='')}/{quote(repo, safe='')}"
        f"/actions/runs/{quote(workflow_run_id, safe='')}"
    )


# --- current-state phase: read the canonical verification lifecycle, never re-derive it ---

# agent_shared.models.verification_claim.VerificationStatus -> Observatory
# phase label. "requested" means CI is outstanding for the published
# commit (session stays running); "passed"/"failed"/"missing" are the three
# terminal verification outcomes session.verification already finalizes
# the session against (agent_control.session.verification.apply_ci_verdict_to_session).
CI_PHASE_BY_CLAIM_STATUS: dict[str, str] = {
    "requested": "verifying",
    "passed": "verified",
    "failed": "failing",
    "missing": "expired",
}


def current_ci_phase_view(
    state_root: Path,
    *,
    project: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Display-safe current-state CI phase for one session, or ``None``.

    Reads :func:`agent_control.session.verification.load_verification_claim`
    directly -- the one durable, canonical artifact CT103 already treats as
    the source of truth for "what did CT102 CI actually decide for this
    exact commit" (``docs/adr/0012-session-verification-evidence-gate.md``).
    This is deliberately *not* a state machine re-derived from replaying
    ``agent.fix_ci_*``/``agent.verification_*`` ledger events in whatever
    order they were projected -- ``apply_ci_verdict_to_session`` already
    refuses to write a new claim once the session is terminal
    (``session.status in TERMINAL_STATUSES``), so reading the current claim
    here can never regress past a terminal outcome: there is only ever one
    current record, and it was never overwritten late.

    Excludes ``claim.limitations`` (free-text; the ledger classification
    table -- :mod:`agent_control.observe.safe_display` -- already marks the
    equivalent ``agent.verification_*`` payload field ``redacted`` for the
    same reason: it can carry exception-derived detail).
    """
    from agent_control.session.verification import load_verification_claim

    claim = load_verification_claim(state_root, project, session_id)
    if claim is None:
        return None
    return {
        "phase": CI_PHASE_BY_CLAIM_STATUS.get(claim.status, claim.status),
        "claim_status": claim.status,
        "claim": claim.claim,
        "source": claim.source,
        "command_id": claim.command_id,
        "artifact": claim.artifact,
        "verdict_revision": claim.verdict_revision,
        "updated_at": claim.updated_at,
    }
