# Slice V7 T05 — Bake-off report

**Status:** Done — DEPLOY_VERIFY PASS  
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
| Epic ledger | T05 Done; epic complete after deploy verify | pass |

## Implementation

- `src/agent_control/bakeoff_report.py` — report builder + gates + negative-transfer notes
- CLI: `agentctl eval bakeoff-report --bundle … --out …`
- Tests: `tests/test_v7_t05_bakeoff_report.py`
- Smoke (for deploy agent): `scripts/_v7_t05_smoke.sh`

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `573a777` (feature `fc446b6`) |
| Verdict | DEPLOY_VERIFY PASS |
| Smoke | `scripts/_v7_t05_smoke.sh 573a777` → `V7_T05_SMOKE_OK profiles 4 gates_ok True` |
| CT103 / CT104 | both `573a777` |
| Evidence | [deploy-verify-v7-t05-20260721.md](handoff/deploy-verify-v7-t05-20260721.md) |
