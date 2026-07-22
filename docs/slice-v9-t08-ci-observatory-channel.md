# Slice V9 T08 -- CT102 CI channel into the Agent Observatory

**Status:** Deploy gate -- pending CT102 Actions / homelab deploy verification
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Depends on:** T03 (done, tip `dae78e3`)
**Ran in parallel with:** T07 (decisions + artifact dispositions) -- disjoint
file ownership, see "Ownership" below
**Hard gates:** H1 (safe-display before store/stream/UI), H3 (projection
identity/sequence), H6 (canonical `AgentSession` state), H7 (fail-open
projector)

## Goal

Project CT102 fix_ci/verification events into the Observatory timeline as a
"CI" log category; derive the current-state panel's CI phase from the
canonical verification lifecycle (never re-derived from raw event replay
order); guarantee a late/duplicate CI verdict cannot regress a terminal
`AgentSession` state; and only ever build a CT102 Actions deep link from
trusted, structured fields -- never the webhook's own free-form `html_url`.

## Ownership (parallel with T07)

- New: `src/agent_control/observe/ci_channel.py`
- Additive: `src/agent_control/observe/safe_display.py` (classification +
  summaries for the 10 `agent.fix_ci_*` types),
  `src/agent_control/observe/projector.py` (run_id/session_id resolution
  fallback), `src/agent_control/observe/ui.py` /
  `src/agent_control/observe/routes.py` (current-state `ci_phase` panel,
  `category` passthrough), `src/agent_control/observe/templates/*.html`
  (one new table row + one bracketed category tag),
  `src/agent_shared/models/observe_event.py` (`category` field)
- New tests: `tests/test_v9_t08_ci_channel.py`,
  `tests/test_v9_t08_ci_projection.py`
- Did **not** touch `src/agent_control/observe/decisions.py`,
  `src/agent_control/observe/artifacts.py`, or their tests -- T07 owns those.

## What shipped

1. **`agent_control/observe/ci_channel.py`** (new) -- the single place that
   teaches the rest of the Observatory pipeline how to read the CT102
   fix_ci_*/verification_* event family:
   - `FIX_CI_EVENT_TYPES` (10 `agent.fix_ci_*` types from
     `agent_shared.models.ci`) / `VERIFICATION_EVENT_TYPES` (4
     `agent.verification_*` types) / `CI_CHANNEL_EVENT_TYPES` (union) and
     `ci_log_category` -- every event in that union gets the Observatory
     `"ci"` log category (`observe_event.v1.category`, additive field).
   - `resolve_ci_run_id` / `resolve_ci_session_id` -- `agent.fix_ci_*`
     events key by `fix_run_id`, not `run_id`/`session_id`. `fix_run_id`
     *is* the underlying fix/repair session's `run_id`
     (`agent_control.session.verification.apply_ci_verdict_to_session`
     already resolves it the same way via `load_session_by_run`); without
     this fallback the generic T02 projector silently skipped every
     `agent.fix_ci_*` event (no resolvable `run_id`).
   - `flatten_observation_fields` -- `agent.fix_ci_observed` carries a
     nested `WorkflowObservation` object; H1's classification table only
     ever inspects top-level payload keys, so this promotes its known-safe
     scalars (`workflow_run_id`, `status`, `conclusion`, `head_sha`, ...) to
     top-level `observation_*` keys *before* classification runs. The
     nested blob's own key is left off the classification table (default-
     deny withholds it, name-only, same as any other unlisted field) --
     there is exactly one path from that nested object to a display
     surface, the explicit flatten, and it is scalars-only.
   - `build_ci_deep_link` -- a CT102 Actions run URL built *only* from
     `Settings.gitea_base_url` and the trusted, structured `repository` /
     `workflow_run_id` fields this codebase itself records for every
     observation. Never reads the webhook's own `html_url`
     (`agent_control.ci.observe.extract_workflow_run_fields`) -- that field
     is not even a parameter this function accepts. Fails closed (`None`)
     on an unset/malformed base URL or either field failing a conservative
     allowlist regex, mirroring `observe_links.py`'s `OBSERVE_PUBLIC_BASE_URL`
     pattern (H8) for this codebase's other externally-reachable link
     surface.
   - `current_ci_phase_view` -- current-state "phase" for panel 1, read
     directly from the canonical `verification_claim.json`
     (`agent_control.session.verification.load_verification_claim`), never
     re-derived from raw `agent.fix_ci_*`/`agent.verification_*` ledger
     replay order. `requested`/`passed`/`failed`/`missing` claim statuses
     map to `verifying`/`verified`/`failing`/`expired` phases.
2. **`safe_display.py`** (additive) -- classification table + summary
   builder entries for all 10 `agent.fix_ci_*` types (all-scalar payloads
   except the flattened `observation_*` fields above; no raw CI log content
   ever appears in these ledger events, only ids/shas/statuses/reason
   codes), `category` set on every `ObserveEventV1` via `ci_log_category`,
   and a `ci_deep_link` display field added to `agent.fix_ci_observed`
   only when `build_ci_deep_link` returns non-`None`.
3. **`projector.py`** (additive) -- `resolve_run_id` falls back to
   `resolve_ci_run_id` when the generic `payload.run_id` lookup is empty;
   `project_ledger_event` falls back to `resolve_ci_session_id` for
   `agent.fix_ci_*` events so H6's `session_observation` refresh still
   fires even though those events never carry a `session_id`.
4. **`ui.py` / `routes.py`** (additive) -- `current_state_view` gained an
   optional `state_root` keyword (backward compatible, defaults to `None` /
   `ci_phase: None`); when passed (the live route always passes it), the
   panel 1 view gains a `ci_phase` key from `current_ci_phase_view`.
   `_parse_event_row` passes through the new `category` field so the
   timeline/live-log templates can tag CI events.
5. **Templates** -- one additive "CI verification" row in panel 1's table,
   and a `[ci]` bracketed tag next to the event type in panels 2 and 4 when
   `category` is set. No other panel/row changed.
6. **Regression proof (goal 3)** -- `verification.apply_ci_verdict_to_session`
   already refuses to write a new claim once
   `session.status in TERMINAL_STATUSES`; because `current_ci_phase_view`
   reads that one current canonical record (never replays events itself),
   a late/duplicate CI verdict structurally cannot regress it --
   `tests/test_v9_t08_ci_projection.py::test_late_duplicate_verdict_does_not_regress_terminal_session_or_ci_phase`
   proves this end to end (terminal `verified` verdict lands, then a stale
   `failing` verdict at an older `verdict_revision` arrives; both the
   session status and the CI phase are unchanged afterward).

## Explicit non-goals honored

- No `observe.sqlite` schema change (`schema.py`/`store.py` untouched) --
  the CI phase is read live from the existing canonical
  `verification_claim.json`, not a new durable projection table.
- No change to `decisions.py`/`artifacts.py` or their tests (T07's surface).
- No change to the SSE wire format (T03) or the five-panel page structure
  (T04) beyond the one additive row/tag described above.
- `agent.fix_ci_repair_*`/`agent.fix_ci_failure_evidence_*` events are
  classified/summarized for the timeline but do not feed
  `current_ci_phase_view` -- that function is deliberately scoped to the
  one canonical verification lifecycle artifact per the ticket's "current-
  state phase from canonical verification lifecycle" wording, not a second,
  competing repair-attempt state machine.

## Evidence pointers

- Code: `src/agent_control/observe/ci_channel.py` (new),
  `src/agent_control/observe/safe_display.py` (diff),
  `src/agent_control/observe/projector.py` (diff),
  `src/agent_control/observe/ui.py` (diff),
  `src/agent_control/observe/routes.py` (diff),
  `src/agent_control/observe/templates/session_detail.html` (diff),
  `src/agent_control/observe/templates/_live_log_rows.html` (diff),
  `src/agent_shared/models/observe_event.py` (diff)
- Docs: this file, `docs/adr/0032-ct102-ci-channel-canonical-phase.md`
- Tests: `tests/test_v9_t08_ci_channel.py` (new),
  `tests/test_v9_t08_ci_projection.py` (new)

## Next coordinator: first actions

1. Deploy-verify on CT103 (+CT104): confirm CI green on the pushed tip,
   `/readyz` unchanged, and that a real CT102 `agent.fix_ci_observed`/
   `agent.fix_ci_verdict_changed` webhook round-trip still projects into
   `observe.sqlite` under the fix session's `run_id` before flipping T08 to
   Done.
2. Once both T07 and T08 are Done, the epic spine
   (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 -> T07 ∥ T08`) is complete.
