# Slice V7 T05 — Bake-off report

**Status:** Implement complete — deploy verify pending (boss / deploy agent)  
**Date:** 2026-07-21  
**Epic ticket:** T05  
**Deps:** T02–T04 Done  

## Goal

Emit `bakeoff_report.v1` comparing profiles A–D longitudinally, with negative-transfer notes and production gates (unbounded recursion OFF; shadow injection ≠ authority; no production memory mutation).

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Artifact | `bakeoff_report.v1` JSON with longitudinal A–D rows | pass (unit) |
| Negative transfer | Structured notes vs baseline A + promotion rule | pass (unit) |
| Gates | `unbounded_recursion=false`; shadow ≠ authority | pass (unit) |
| Memory | `production_memory_touched=false`; namespaces under `bakeoff/*` | pass (unit) |
| CLI | `agentctl eval bakeoff-report --bundle …` | pass |
| Epic ledger | Not marked Done / complete by implement agent | honor |

## Implementation

- `src/agent_control/bakeoff_report.py` — report builder + gates + negative-transfer notes
- CLI: `agentctl eval bakeoff-report --bundle … --out …`
- Tests: `tests/test_v7_t05_bakeoff_report.py`
- Smoke (for deploy agent): `scripts/_v7_t05_smoke.sh`

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | *(pending deploy pin)* |
| Verdict | pending |
| Smoke | `scripts/_v7_t05_smoke.sh <tip>` |
| CT103 / CT104 | pending |
