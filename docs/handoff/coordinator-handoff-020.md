# Handoff — coordinator-handoff-020

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 020 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | V7 T04 |
| Tip SHA (ACP) | `47cde2b` |
| Epic | V7 recursive context evaluation & controller bake-off |
| `stopped_reason` | `deploy_gate_pending` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-020.md
tickets_done: 3 / 5
next_ticket_id: T04
blocker: none
stopped_reason: deploy_gate_pending
```

## Slice outcome

- Goal completed: bake-off memory fork/reset isolation under `bakeoff/*`; prod namespace refused.
- Slice doc: docs/slice-v7-t04-memory-isolation.md
- Deploy verify: pending (separate agents)
- CT103 / CT104: pending pin of `47cde2b`

## Evidence pointers

- Unit: tests/test_v7_t04_memory_isolation.py
- Smoke: scripts/_v7_t04_smoke.sh
- Module: src/agent_control/bakeoff_memory.py

## Decisions the next coordinator must honor

1. Bake-off writes/resets only under `bakeoff/*`; never open production SQLite from bake-off paths.
2. `run_all_profiles_against_bundle` shares one facade and asserts pairwise writeback isolation.
3. Do not mark T04 Done until deploy verify PASS; T05 is next after Done.

## Next coordinator: first actions

1. Deploy/pin CT103+CT104 to `47cde2b`; run `scripts/_v7_t04_smoke.sh 47cde2b`.
2. Fill DEPLOY_VERIFY; boss marks T04 Done.
3. Start V7 T05 bake-off report (deps T02–T04).

## Open risks (one line each)

- Isolation is in-process facade for dry-run; live controller writebacks must keep the same namespace gate when T05 enables them.
