# Slice V7 T04 — Memory isolation (bake-off namespaces)

**Status:** Code complete — deploy verify pending  
**Date:** 2026-07-21  
**Epic ticket:** T04  
**Deps:** T01  

## Goal

Fork/reset bake-off memory namespaces via `memory_namespace` metadata so profile A–D runs cannot see each other's writebacks, and the production memory namespace / SQLite store stays untouched.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Namespace gate | Writes/resets only under `bakeoff/*`; refuse `production` | pass |
| Fork/reset | `fork(source→dest)` + `reset(ns)` APIs; empty fork when no seed | pass |
| Cross-profile | Profile writebacks invisible to sibling profile namespaces | pass |
| Production | `production_memory_touched=false`; never open prod `MemoryStore` | pass |
| Embed | Isolation block on `bakeoff_run.v1`; shared facade across A–D | pass |
| Tests | Unit coverage for refuse-prod, isolation, multi-profile | pass |

## Implementation

- `src/agent_control/bakeoff_memory.py` — in-process namespaced store (no prod SQLite)
- Wired into `bakeoff_profiles.run_profile_against_bundle` / `run_all_profiles_against_bundle`
- CLI bakeoff-run emits `memory_isolation` block
- Tests: `tests/test_v7_t04_memory_isolation.py`
- Smoke: `scripts/_v7_t04_smoke.sh`

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `47cde2b` |
| Verdict | pending (separate deploy agents) |
| Smoke | `scripts/_v7_t04_smoke.sh 47cde2b` |
| CT103 / CT104 | pending |
