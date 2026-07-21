# Slice V7 T03 — Bake-off metrics

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T03  
**Deps:** T01  

## Goal

Emit documented `bakeoff_metrics.v1` JSON per profile/bundle run: CT102 verified success, repair iterations, fallback count, policy violations, tokens, cost, wall time.

## Acceptance

| Check | Expected |
|-------|----------|
| Schema | `bakeoff_metrics.v1` with documented field contract |
| Source | Derived from verified `eval_bundle.v1` timeline/stages |
| Embed | Attached to `bakeoff_run.v1` and written as sidecar JSON |
| CLI | `agentctl eval bakeoff-metrics --bundle …` |
| Safety | `production_memory_touched=false` |

## Deploy smoke

1. Fixture with repair/fallback/policy/ct102 events → non-zero counts where expected
2. Profile run embeds metrics; sidecar file present
