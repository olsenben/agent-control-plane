# Slice V9 T01 — observe_event.v1 safe-display contract

**Status:** done — 2026-07-22
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Hard gate:** H1 — safe-display contract before any sqlite/SSE/UI work (T02–T04)
**ADR:** [0027-observe-event-safe-display-contract.md](adr/0027-observe-event-safe-display-contract.md)
**Producer inventory:** [observe-producer-coverage-v9-t01.md](observe-producer-coverage-v9-t01.md)

## Problem

`observe/projection.py` (V6 T01) built its timeline by copying the raw
ledger `payload` dict of every matched event straight into the API/SSE/UI
response. That is fine while the only producers are curated CT103
correlation events, but V9 adds T02 (sqlite persistence), T03 (protected
SSE), and T04 (five-panel UI) on top of the *same* read path, and future
producer events (approvals, model routing, CI fix-loop, sandbox, publish)
are not guaranteed to stay payload-clean forever. Building storage/streaming/
UI first and adding redaction later means every event type added in the
interim is raw-by-default. H1 requires the safe-display contract to exist
and be wired in *first*.

## What shipped

1. **`agent_shared.models.observe_event.ObserveEventV1`** — the
   `observe_event.v1` schema every display surface consumes. Never carries a
   raw `payload` field; carries `display_fields` (vetted values only),
   `summary`, `known_type`, and three name-only audit lists
   (`redacted_field_names`, `metadata_only_field_names`,
   `prohibited_field_names`).
2. **`agent_control.observe.safe_display`** — the classification + rendering
   engine:
   - `is_prohibited_field_name` — global keyword filter (token, secret,
     password, credential, authorization, cookie, api_key, private_key,
     ssh_key, bearer, header, env, prompt, stdout/stderr, raw_output/raw_log,
     tool `args`) that forces `prohibited` regardless of any per-type table
     entry. This is the layer the unit fixtures pin down.
   - A per-event-`type` field table covering every event type currently
     wired into the Observatory timeline (session lifecycle, memory/context/
     recursive-context, verification claims, `control_decision`,
     `injection_assessment`, `run_completed`). Each field is
     `allowlisted` / `redacted` / `metadata_only`; anything absent is
     `prohibited` by default.
   - `safe_display_event` / `safe_display_events` — the normalizer.
     Unknown `type` (not in the table) → zero payload values exposed, ever;
     only field names land in `prohibited_field_names`.
3. **`observe/projection.py` wired** — `build_observation_projection` now
   normalizes every matched ledger event through `safe_display_event`
   before it is added to `ObservationProjection.events`. This is the single
   builder used by the CLI (`agentctl observe show`), the Observatory API/UI/
   SSE routes, and `agent_control.eval_export`; there is no code path in this
   module that returns a raw ledger payload.
4. **Producer-coverage inventory** — every named V9 domain (CT103, CT104,
   model, context, sandbox, publish, CI) classified into
   `existing_typed_event` / `existing_artifact_row` /
   `new_producer_event_required` / `unsupported_unknown`. Three
   `existing_typed_event` groups (approval lifecycle, model routing, CI
   fix-loop) are not yet in the classification table; they render via the
   safe unknown-type fallback today and are explicitly tracked for the
   slices that build UI on top of them (T07, T04, T08 respectively) so no
   later slice can assume "it's already an event" implies "it's already
   safe to render richly."
5. **Unit fixtures** (`tests/test_v9_t01_safe_display.py`) proving:
   - the keyword filter catches representative prompt/token/env/header/
     tool-cred field names, including ones that don't exist in any producer
     today (defense against future regressions);
   - the filter overrides a mistaken per-type allowlist entry;
   - an unknown event type never exposes any payload value, only names;
   - a known type (`agent.session_started`) still blocks a simulated
     producer bug that adds `final_prompt` / `gitea_bot_token` / `tool_args`;
   - `agent.injection_assessment`'s `matched_regions`/`detail` (which can
     carry raw untrusted issue/PR excerpts, ADR-0026) render as
     count-only descriptors, never the snippet text;
   - `redacted` fields (`reason`) render as a fixed placeholder, not the
     underlying exception text;
   - end-to-end: `build_observation_projection` on a mix of `session_started`
     + `control_decision` + a simulated unregistered future event type never
     leaks the planted secret/prompt strings anywhere in the serialized
     projection, and no event in the timeline carries a `payload` key at all.

## Explicit non-goals (deferred to later V9 tickets)

- No `observe.sqlite` persistence (T02).
- No Gitea OAuth / 401/403/503 shell (T05).
- No protected SSE subscribe-first + Redis id-notify (T03).
- No Jinja/HTMX five-panel UI (T04).
- No Gitea `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` (T06).
- Approval-lifecycle, model-routing, and CI fix-loop event types are not yet
  added to the classification table (see inventory); they are safe by the
  unknown-type fallback but not yet richly displayable. This is intentional
  — T01 scope is the *contract*, not exhaustive classification of every
  event type in the codebase.

## Known side effect

`agent_control.eval_export.build_eval_bundle` and `bakeoff_metrics.py` read
`projection.events[i]["payload"]`. Since the projection no longer carries raw
payloads, `eval_export.py` now maps `display_fields` into that same
`"payload"` key so downstream consumers (bake-off metrics extraction,
`test_v7_t03_bakeoff_metrics.py`) keep working unchanged — they now read the
same display-safe values the UI will, which is a strictly safer default and
was verified not to change any of the currently-asserted bake-off metric
values (fields the metrics extractor reads — `kind`, `summary`,
`policy_decision` — are all `allowlisted` for `agent.control_decision`).
`tests/test_v6_t06_injection_shadow.py` was updated to read
`display_fields` instead of the removed `payload` key.

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 685 passed
```

New test file: `tests/test_v9_t01_safe_display.py` (10 tests, all passing).
