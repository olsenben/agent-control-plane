# Slice V7 T03 — Bake-off metrics

**Status:** Done — deploy verify PASS tip `198eabf` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T03  
**Deps:** T01  

## Goal

Emit documented `bakeoff_metrics.v1` JSON per profile/bundle run: CT102 verified success, repair iterations, fallback count, policy violations, tokens, cost, wall time.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Schema | `bakeoff_metrics.v1` with documented field contract | pass |
| Source | Derived from verified `eval_bundle.v1` timeline/stages | pass |
| Embed | Attached to `bakeoff_run.v1` and written as sidecar JSON | pass |
| CLI | `agentctl eval bakeoff-metrics --bundle …` | pass |
| Safety | `production_memory_touched=false` | pass |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `198eabf` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V7_T03_SMOKE_OK repair 1 fallback 1` |
| CT103 / CT104 | `198eabf` / `198eabf` |
