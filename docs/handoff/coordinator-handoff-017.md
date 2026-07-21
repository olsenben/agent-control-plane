# Handoff — coordinator-handoff-017

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 017 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | V7 T01 |
| Tip SHA (ACP) | `b1a8a38` |
| Epic | V7 recursive context evaluation & controller bake-off |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-017.md
tickets_done: 1 / 5
next_ticket_id: T02
blocker: none
stopped_reason: context_handoff
```

## Slice outcome

- Goal completed: eval_bundle.v1 → inspect_adapt.v1 with SHA fail-closed + CLI.
- Slice doc path: docs/slice-v7-t01-inspect-adapter.md
- Deploy verify: pass tip `b1a8a38`
- CT103 tip / CT104 tip: `b1a8a38` / `b1a8a38`

## Evidence pointers

- Unit: tests/test_v7_t01_inspect_adapter.py
- Smoke: scripts/_v7_t01_smoke.sh → V7_T01_SMOKE_OK

## Decisions

- Framework-neutral `inspect_adapt.v1` JSON; hard dependency on `inspect_ai` deferred (soft import only).
- Bake-off namespace default: `bakeoff/<bundle.ns>/<run_id>`.

## First actions for next wave

1. Implement V7 T02 profiles A–D configs against same fixture bundle.
2. Do not reopen residual QA items from qa-v6-ledger (deferred).
