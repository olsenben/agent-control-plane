# Slice V8 T01 — Homelab DUR soak / restart

**Status:** Done — deploy verify PASS tip (docs/script) after soak on live baseline `c274c07` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T01  
**Deps:** none  

## Goal

Bounce CT103 control-plane (+ optional light CT104 worker restart) and prove durable ledger sequence, observation projections, budget keys, and `/readyz` (redis + state) survive with no silent truncation.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Scripted restart soak | CT103 `control-plane` restart under script | pass |
| Ledger continuity | Seeded event `ledger_sequence` values unchanged after restart | pass |
| Counter continuation | Post-restart append == `max_soak_seq + 1` | pass (2 → 3) |
| Projection rebuild | Same event ids / sequences / `max_sequence` after restart | pass |
| Budget durability | Attempts + idempotency key survive; no double-charge | pass |
| `/readyz` | redis + state_dir ok before and after | pass (overall degraded: model_2070) |
| Optional CT104 | Light `worker-report` restart; CT103 state intact; no write tokens | pass |

## Implementation

- `scripts/_v8_t01_dur_soak.sh` — seed → fingerprint → restart CT103 control-plane (+ worker-state) → verify → optional CT104 `worker-report` restart
- No product-code change required (unit DUR already PASS in V6)

## Soak evidence (live)

| Field | Value |
|-------|-------|
| Host tip at soak | CT103 `c274c07` |
| Soak tag | `20260721T231610Z-48cad1fd` |
| Project | `ai-sdlc-lab/demo-app` |
| Sequences | a=1, b=2; post-restart append=3 |
| Budget | `run-v8-t01-dur-20260721T231610Z-48cad1fd` attempts=1 idempotent |
| Markers | `V8_T01_SEED_OK` / `V8_T01_DUR_VERIFY_OK` / `NFS_CROSSCHECK_OK` / `V8_T01_DUR_SOAK_PASS` |

## Deploy verification

See [docs/handoff/deploy-verify-v8-t01-20260721.md](handoff/deploy-verify-v8-t01-20260721.md).
