---
id: ADR-0032
title: CT102 CI channel projects into the Observatory via canonical state, never event replay
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_control/observe/ci_channel.py"
    - "src/agent_control/observe/safe_display.py"
    - "src/agent_control/observe/projector.py"
    - "src/agent_control/observe/ui.py"
symbols:
  - resolve_ci_run_id
  - resolve_ci_session_id
  - flatten_observation_fields
  - build_ci_deep_link
  - current_ci_phase_view
decision_type: data
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-22
agent_visibility:
  - review
  - developer
---

# Context

ADR-0028 flagged this exact follow-up when T02 shipped `observe.sqlite`:
"[the synchronous fail-open projection] acceptable at homelab single-writer
scale, revisit if T08 (CT102 CI volume) changes that." T08 is that revisit
for the CT102 fix_ci_*/verification_* event family
(`agent_shared.models.ci`, `agent_control.ci.events`,
`agent_control.session.verification`).

Two problems specific to this event family, neither solved by the existing
T01/T02 machinery as-is:

1. **Identity mismatch.** T02's generic projector
   (`observe.projector.project_ledger_event`) resolves `run_id` from
   `payload.run_id`. Every `agent.fix_ci_*` event instead keys by
   `fix_run_id` and never carries `session_id` at all -- unmodified, every
   one of these events is silently out of scope (no resolvable `run_id`),
   the same "skip, not an error" path already used for approval events
   keyed by issue number.
2. **State-machine temptation.** The ticket asks for a "current-state
   phase from canonical verification lifecycle" and requires that a
   late/duplicate CI verdict never regress a terminal `AgentSession`.
   The event family includes ten `agent.fix_ci_*` event types plus four
   `agent.verification_*` types spanning observation, verdict-change,
   failure-evidence, and repair-attempt sub-flows -- replaying all of that
   in projection order to derive "the current phase" would mean re-deriving
   ordering/regression guarantees session/verification.py already owns and
   already enforces at the one point that matters (before writing a new
   canonical claim).

# Decision

1. **`fix_run_id` is the session's `run_id`; teach the projector a
   fallback, not a new identity scheme.** `ci_channel.resolve_ci_run_id`
   maps `payload.fix_run_id` to `run_id` for the ten `agent.fix_ci_*` types
   only; `observe.projector.resolve_run_id` tries the generic
   `payload.run_id` lookup first and falls back to this only when that
   comes up empty. `ci_channel.resolve_ci_session_id` best-effort resolves
   `session_id` via `agent_control.session.storage.load_session_by_run` --
   the exact same resolution `session.verification.apply_ci_verdict_to_session`
   already performs for the same `fix_run_id`. H3's identity/sequence
   invariants (`UNIQUE(run_id, source_kind, source_event_id)`,
   per-run `projection_sequence`) are unchanged; this only supplies the
   `run_id` the existing machinery needs.
2. **Current-state CI phase reads the one canonical record, never replays
   events.** `ci_channel.current_ci_phase_view` reads
   `session.verification.load_verification_claim` -- the durable artifact
   ADR-0012 already established as the source of truth for "what did CT102
   CI decide for this exact commit." `apply_ci_verdict_to_session` already
   refuses to write a new claim once
   `session.status in TERMINAL_STATUSES`; because the Observatory phase is
   a live read of that same one record, a late/duplicate verdict has
   nothing to regress -- there is exactly one current record, and it was
   never overwritten late. This is deliberately *not* a second state
   machine derived from replaying `agent.fix_ci_*`/`agent.verification_*`
   rows in projection order.
3. **Nested `WorkflowObservation` is flattened before classification, not
   given a second, less-reviewed path to display data.**
   `agent.fix_ci_observed` is the one event in this family carrying a
   nested object. H1's classification table (`safe_display.classify_field`)
   only ever inspects top-level payload keys and default-denies anything
   absent from a type's table. `ci_channel.flatten_observation_fields`
   promotes exactly the known-safe `WorkflowObservation` scalars
   (`workflow_run_id`, `status`, `conclusion`, `head_sha`, `pr_number`,
   `api_verification_status`, `observed_at`, `workflow_id`, `path`,
   `display_name`) to top-level `observation_*` keys before classification
   runs; the raw nested key is left off the table entirely (default-deny
   withholds it, name-only). There is exactly one flatten function, called
   from exactly one place (`safe_display_event`), so there is exactly one
   thing to audit for "did this leak the raw blob" -- it does not.
4. **CI deep links interpolate only trusted, structured, server-recorded
   fields.** `ci_channel.build_ci_deep_link` accepts `repository` and
   `workflow_run_id` -- both fields this codebase itself writes into the
   `agent.fix_ci_*` ledger events from `PendingCiRecord`/the API-confirmed
   `WorkflowObservation` (`agent_control.ci.observe._confirm_via_api`
   prefers the Gitea API response over the raw webhook when they
   disagree). It has no `html_url` parameter at all -- the webhook's own
   free-form `html_url`/`event` fields
   (`agent_control.ci.observe.extract_workflow_run_fields`) are never read
   by this module. Both accepted fields are re-validated against a
   conservative allowlist regex inside the function itself (defense in
   depth even if a caller already filtered), and the link is omitted
   entirely (`None`) on an unset/malformed `GITEA_BASE_URL` or either field
   failing that check -- the same fail-closed shape as `observe_links.py`'s
   `OBSERVE_PUBLIC_BASE_URL` (H8), applied to this codebase's other
   externally-reachable link surface.
5. **No new durable schema.** The CI phase is a live read of the existing
   `verification_claim.json`, not a new `observe.sqlite` table/column --
   `schema.py`/`store.py` (T02's ADR-0028 surface) are untouched. The `"ci"`
   log category and the CI deep link are both additive fields on the
   existing `observe_event.v1` contract (`category: str | None = None`,
   an extra `display_fields["ci_deep_link"]` key), never a breaking change
   to a field any existing consumer already reads.

# Consequences

- Positive: T08 closes ADR-0028's own flagged follow-up -- CT102 CI events
  are no longer silently out of scope for the Observatory timeline, and the
  volume/identity concern that ADR raised is resolved by reusing the
  existing per-run projection path, not a parallel one.
- Positive: "no terminal regression" is a structural property of reading
  one canonical record, not a property this ticket has to separately
  enforce/test against every possible event-arrival order; the regression
  test in `tests/test_v9_t08_ci_projection.py` demonstrates the property,
  it does not implement the guarantee.
- Negative: `current_ci_phase_view` intentionally does not surface
  in-flight repair-attempt sub-state (`agent.fix_ci_repair_requested/
  started/pushed/exhausted/stale`) as part of "phase" -- those events are
  visible in the Observatory timeline (categorized `"ci"`) but not folded
  into panel 1's single phase label. A future ticket that wants a richer
  "repair attempt N/M in progress" current-state phase should extend
  `current_ci_phase_view`'s return shape, not introduce a second phase
  concept.
- Follow-up: if a future CT102 CI event ever needs to carry a genuinely
  free-text/log-shaped field (none of the ten `agent.fix_ci_*` types do
  today), it must be classified `redacted` or `metadata_only` in
  `safe_display.py`, the same as any other event family -- this ADR's
  "no raw CI log content ever appears in these ledger events" observation
  is a fact about the current event shapes, not an exemption from H1.
