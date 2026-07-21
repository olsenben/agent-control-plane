# Handoff — coordinator-handoff-022

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 022 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | V8 T01 |
| Tip SHA (ACP) | (commit after push; live soak on `c274c07`) |
| Epic | V8 residual QA |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-022.md
tickets_done: 1 / 4
next_ticket_id: T02 (or T03 if WaitingHuman wave allowed)
blocker: none
stopped_reason: context_handoff
```

## Slice outcome

- Goal completed: live CT103 control-plane bounce proved ledger sequence, projections, budget keys, and `/readyz` redis+state survive; optional CT104 worker-report restart safe.
- Slice doc: docs/slice-v8-t01-dur-soak.md
- Deploy verify: PASS — [deploy-verify-v8-t01-20260721.md](deploy-verify-v8-t01-20260721.md)
- CT103 tip at soak: `c274c07`; CT104 observed tip `3651bfe` (N/A for code pin this slice)

## Evidence pointers

- Soak script: scripts/_v8_t01_dur_soak.sh
- Markers: `V8_T01_SEED_OK`, `V8_T01_DUR_VERIFY_OK`, `NFS_CROSSCHECK_OK`, `V8_T01_DUR_SOAK_PASS`
- Soak tag: `20260721T231610Z-48cad1fd` (demo-app seq 1→2→3)
- Deploy verify: docs/handoff/deploy-verify-v8-t01-20260721.md

## Decisions the next coordinator must honor

1. T01 is Done — do not re-open DUR soak unless a later tip regresses durability.
2. Do not touch T02–T04 ownership from this handoff; T02/T04 may need WaitingHuman.
3. CT104 tip may lag CT103; state durability proof is NFS on CT103.

## Next coordinator: first actions

1. Boss: mark T01 Done in boss-ledger-v8.md + qa-v8-ledger.md QA-V8-T01 PASS.
2. Start T02 or T03 per parallelism policy (not this agent).

## Open risks (one line each)

- `/readyz` remains overall degraded while model_2070 is unreachable (redis+state ok).
- CT104 tip drift vs CT103 observed during soak — track if a later slice requires dual pin.
