# Handoff — coordinator-handoff-026

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 026 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T01 |
| Tip SHA (ACP) | `4dc32e5` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-026.md
ticket: T01
status: Deploy gate
tip_sha: 4dc32e5
tests: 685 passed
ruff: All checks passed!
blocker: none
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- `observe_event.v1` (`agent_shared/models/observe_event.py`) + `safe_display`
  normalizer (`agent_control/observe/safe_display.py`): four-tier field
  classification (allowlisted/redacted/metadata_only/prohibited), global
  secret/prompt/token/header/env/tool-arg keyword filter as a second
  independent defense layer, per-event-type default-deny table.
- `observe/projection.py` wired: `build_observation_projection` now returns
  display-safe events only; no code path returns a raw ledger `payload`.
  Unknown event types expose zero payload values, only field names.
- Producer-coverage inventory
  ([docs/observe-producer-coverage-v9-t01.md](../observe-producer-coverage-v9-t01.md))
  covering CT103/CT104/model/context/sandbox/publish/CI in the four required
  buckets; 3 existing typed-event groups (approval lifecycle, model routing,
  CI fix-loop) explicitly flagged as not-yet-classified (safe via unknown-type
  fallback) for T04/T07/T08 to close before claiming rich UI coverage.
- ADR-0027 accepted; slice doc
  [docs/slice-v9-t01-observation-event-contract.md](../slice-v9-t01-observation-event-contract.md).
- New tests: `tests/test_v9_t01_safe_display.py` (10 tests) proving prompts/
  tokens/env/headers/tool creds excluded, including a simulated end-to-end
  producer-bug scenario through `build_observation_projection`.
- Fixed collateral: `eval_export.py` now maps `display_fields` into its
  timeline `payload` key (bake-off metrics extractor reads `kind`/`summary`/
  `policy_decision`, all allowlisted for `agent.control_decision` — no
  behavior change to existing bake-off metric assertions);
  `test_v6_t06_injection_shadow.py` updated to read `display_fields` instead
  of the removed raw `payload` key.
- `ruff check .` clean; full suite `685 passed`.
- Committed on `main` (`4dc32e5`) and pushed to `origin/main` so CT102
  Actions run per the homelab deploy pattern.

## Explicit non-goals honored

- No `observe.sqlite` (T02), no Gitea OAuth shell (T05), no SSE/Redis (T03),
  no UI (T04), no Gitea `extra_tabs` (T06). Existing auth routes
  (`observe/auth.py`) untouched and still passing their existing tests.

## Evidence pointers

- Code: `src/agent_shared/models/observe_event.py`,
  `src/agent_control/observe/safe_display.py`,
  `src/agent_control/observe/projection.py` (diff only),
  `src/agent_control/eval_export.py` (diff only)
- Tests: `tests/test_v9_t01_safe_display.py`,
  `tests/test_v6_t06_injection_shadow.py` (updated assertion)
- Docs: ADR-0027, `docs/observe-producer-coverage-v9-t01.md`,
  `docs/slice-v9-t01-observation-event-contract.md`

## Decisions the next coordinator must honor

1. Any new ledger event type must get a `safe_display` classification table
   entry before a later slice (T02/T03/T04) renders it richly; absence of an
   entry is safe (unknown-type fallback) but not acceptable as a permanent
   state for a UI panel.
2. `observe/projection.py` is the single choke point — do not add a second
   code path in T02/T03/T04 that reads raw ledger `payload` directly for
   display purposes.
3. Approval lifecycle, model routing, and CI fix-loop event types still need
   classification table entries (owners: T07, T04/T07, T08 respectively per
   the producer inventory) before those slices claim full Observatory
   coverage.

## Next coordinator: first actions

1. Confirm CT102 Actions run green on tip `4dc32e5` (push already done).
2. Start T02 (`observe.sqlite` idempotent display-safe projection) — must
   persist `observe_event.v1` rows, not raw payload (ADR-0027 consequence #6).
3. Flip T01 → Done in `boss-ledger-v9.md` once deploy verification (CT102 CI
   green, and/or CT103 homelab smoke if the boss requires it for this ticket)
   is recorded.

## Open risks (one line each)

- Three known-typed-event groups are not yet in the classification table;
  if a future slice wires them into the UI without adding table entries
  first, they will render as opaque unknown-type placeholders, not richly
  displayed (safe, but confusing without diagnosis of the inventory doc).
- `eval_export.py` bake-off metrics now depend on `agent.control_decision`
  fields staying `allowlisted`; any future re-classification of `kind`/
  `summary` to a stricter tier would silently zero out `repair_iterations`/
  `fallback_count`/`policy_violations` in bake-off metrics extraction.
