# Handoff -- coordinator-handoff-032

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 032 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T07 + T08 (parallel wave, combined handoff -- shared-file entanglement in `routes.py`/`session_detail.html` made a clean two-commit split impractical) |
| Tip SHA (ACP) | `df1d6d8` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-032.md
ticket: T07 + T08
status: Deploy gate
tip_sha: df1d6d8
tests: 890 passed
ruff: All checks passed! (tracked files; scripts/_v9_t04_smoke_remote.py is an
      untracked scratch script excluded from this commit per instructions
      and has one pre-existing, unrelated F841)
blocker: none
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

**T07 -- Decisions + artifact dispositions (H5 artifact trust):**

- New `agent_control/observe/decisions.py` -- `observe_decision.v1`, a
  decision-scoped safe-display choke point sibling to `safe_display.py`.
  Allowlists exactly four `ControlDecision.metadata` sub-keys (`why`,
  `evidence`, `alternatives_rejected`, `remaining_uncertainty`); every other
  key, including one that is itself chain-of-thought-shaped by name, is
  withheld by name only. `ObserveDecisionV1` has no `chain_of_thought` field.
- New `agent_control/observe/artifacts.py` -- the three artifact
  dispositions (`metadata_only`/`redacted_text_view`/
  `downloadable_redacted_copy`) with a full path/symlink/size/MIME/hash
  trust-gate chain, all fail-closed to "not available"; an opaque
  `artifact_id` that never accepts or derives a filesystem path from the
  request; redaction reuses `safe_display.is_prohibited_field_name`; there
  is no code path anywhere in this module that returns an artifact's
  original bytes.
- Two new routes (`.../artifacts/{artifact_id}/view` and `/download`), same
  auth matrix as every other Observatory route. Panels 3 and 5 wired to
  real data; a session with zero decisions/artifacts still renders the
  pre-existing T04 placeholder text (backward compatible).
- Tests: `tests/test_v9_t07_decisions.py` (17), `tests/test_v9_t07_artifacts.py`
  (21).

**T08 -- CT102 CI truth-loop into the Observatory (H1/H3/H6):**

- New `agent_control/observe/ci_channel.py` -- teaches the generic projector
  to resolve `agent.fix_ci_*` events (keyed by `fix_run_id`, never
  `run_id`/`session_id`) as an additive fallback only, tried after the
  generic `payload.run_id` lookup; flattens `agent.fix_ci_observed`'s nested
  `WorkflowObservation` to top-level `observation_*` scalars before H1
  classification runs; builds a CT102 Actions deep link only from
  `Settings.gitea_base_url` + the trusted, structured `repository`/
  `workflow_run_id` fields this codebase already records (never the
  webhook's own `html_url`); reads panel 1's CI phase live from the
  canonical `verification_claim.json` (never re-derived from event replay
  order, so a late/duplicate CI verdict structurally cannot regress it --
  `apply_ci_verdict_to_session` already refuses to write past a terminal
  session).
- `safe_display.py` gains a full classification table + summary builders
  for all 10 `agent.fix_ci_*` types, plus a `category` tag (`"ci"`) on the
  whole `agent.fix_ci_*`/`agent.verification_*` channel
  (`ObserveEventV1.category`, additive).
- `projector.py`/`ui.py`/`routes.py`/templates: additive-only wiring
  (`resolve_run_id` fallback, `current_state_view`'s optional `state_root`
  keyword and `ci_phase` key, `[ci]` tag on timeline/live-log rows).
- ADR-0032 accepted (`docs/adr/0032-ct102-ci-channel-canonical-phase.md`).
- Tests: `tests/test_v9_t08_ci_channel.py` (37, unit-level: module
  resolution/allowlist/deep-link/phase-mapping + safe_display/projector
  integration + end-to-end page rendering) and
  `tests/test_v9_t08_ci_projection.py` (7, full real-session lifecycle:
  H3 identity + H6 session_observation refresh, idempotent replay, and the
  regression proof that a late/duplicate CI verdict at an older
  `verdict_revision` cannot regress a terminal `AgentSession` or the
  Observatory's `ci_phase`).

**Why one combined handoff, not two tickets in two commits:** T07 and T08
were built by parallel agents with disjoint *new*-file ownership
(`decisions.py`/`artifacts.py` vs. `ci_channel.py`), but both tickets touch
the same three shared files (`routes.py`, `ui.py`'s caller in `routes.py`,
`session_detail.html`) in adjacent, interleaved hunks (for example, the
`observe_session_page` context dict has T08's `state_root=` keyword on one
line and T07's `decisions=`/`artifacts=` keys on the next two). Splitting
that cleanly into two independent, individually-buildable commits would
require manual sub-hunk surgery with no real benefit; both tickets landed in
one `feat(v9-t07+t08)` commit (`df1d6d8`), preceded by a separate,
cleanly-separable `V9 T06: deploy-verify closeout` commit (`d1df0b8`) that
had been sitting uncommitted from the previous wave.

## Explicit non-goals honored

- No raw artifact download anywhere (T07); no new `observe.sqlite` schema
  (T08 reads the existing canonical `verification_claim.json` live, never a
  new durable projection table).
- No change to the generic projector's contract for any event type outside
  `FIX_CI_EVENT_TYPES`/`CI_CHANNEL_EVENT_TYPES` (T08); no widening of the
  generic `observe.sqlite` `metadata_only` classification of
  `agent.control_decision.metadata` (T07 is a separate, additive read path
  over the raw ledger).
- No CI deep link built from the webhook's own `html_url` (T08's
  `build_ci_deep_link` does not even accept that parameter).

## Evidence pointers

- Code: `src/agent_control/observe/decisions.py` (new),
  `src/agent_control/observe/artifacts.py` (new),
  `src/agent_control/observe/ci_channel.py` (new),
  `src/agent_control/observe/routes.py` (diff),
  `src/agent_control/observe/ui.py` (diff),
  `src/agent_control/observe/safe_display.py` (diff),
  `src/agent_control/observe/projector.py` (diff),
  `src/agent_control/observe/templates/session_detail.html` (diff),
  `src/agent_control/observe/templates/_live_log_rows.html` (diff),
  `src/agent_control/observe/templates/artifact_redacted_view.html` (new),
  `src/agent_shared/models/observe_event.py` (diff, `category` field)
- Docs: `docs/slice-v9-t07-decisions-artifacts.md`,
  `docs/slice-v9-t08-ci-observatory-channel.md`,
  `docs/adr/0032-ct102-ci-channel-canonical-phase.md`,
  `docs/adr/summary.md` (index entry)
- Tests: `tests/test_v9_t07_decisions.py` (17),
  `tests/test_v9_t07_artifacts.py` (21),
  `tests/test_v9_t08_ci_channel.py` (37),
  `tests/test_v9_t08_ci_projection.py` (7)

## Decisions the next coordinator must honor

1. `agent_control/observe/decisions.py` and `agent_control/observe/artifacts.py`
   are the only paths from `ControlDecision.metadata` / `SessionArtifactRef`
   to a display surface. Any future change to what a decision/artifact
   panel shows must extend these modules' own allowlists, never read the
   raw ledger/artifact bytes from a route or template directly.
2. `agent_control/observe/ci_channel.py` is the only place that knows
   `agent.fix_ci_*` events key by `fix_run_id`. Any future CT102 CI event
   type must be added to `FIX_CI_EVENT_TYPES` (or the appropriate sibling
   set) and given its own `safe_display.py` classification table entry --
   never assumed safe by omission.
3. `current_ci_phase_view` is deliberately scoped to the one canonical
   verification lifecycle artifact, not a second state machine over
   `agent.fix_ci_repair_*` sub-events. A future ticket that wants a richer
   "repair attempt N/M" current-state phase should extend this function's
   return shape, not introduce a competing phase concept (see ADR-0032
   Consequences).
4. `build_ci_deep_link` must never be given an `html_url`-shaped parameter;
   any future deep-link surface must build only from server-side settings
   and already-trusted, structured, allowlisted fields.

## Next coordinator: first actions

1. `git push origin main` (already done as part of this handoff's landing;
   confirm CT102 Actions runs green on `df1d6d8`).
2. Deploy-verify on CT103 (+CT104): confirm CI green on the pushed tip,
   `/readyz` unchanged, panel 3/5 render real decision/artifact content for
   a session that has them and the pre-existing placeholders for one that
   does not, no raw artifact bytes reachable from any route, and a live (or
   replayed) CT102 `agent.fix_ci_observed`/`agent.fix_ci_verdict_changed`
   event projects into `observe.sqlite` with `category=ci` and shows up on
   the session's timeline/panel 1 -- before flipping both T07 and T08 to
   Done.
3. Once both T07 and T08 are Done, the epic spine
   (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 -> T07 ∥ T08`) is complete;
   close the V9 epic.

## Open risks (one line each)

- `current_ci_phase_view` does not surface in-flight repair-attempt
  sub-state as part of "phase" -- those events are visible in the timeline
  (`category=ci`) but not folded into panel 1's single phase label (by
  design, see ADR-0032).
- Neither ticket has a live CT102 Actions round-trip smoke yet (unit +
  integration tests only) -- that is exactly what CT103/CT104 deploy-verify
  must confirm before Done.
