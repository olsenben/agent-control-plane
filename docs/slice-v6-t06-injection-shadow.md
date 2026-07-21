# Slice V6 T06 — Injection scanner shadow evaluation

**Status:** Done — deploy verify PASS tip `6cc8264` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T06  
**Deps:** T01, T03 Done  

## Goal

Shadow-mode modular injection detection (`injection_assessment.v1`) visible in Observatory; never grants authority. Blocking deferred.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Shadow assessment | risk/categories/matched_regions/recommended_action | pass |
| Authority | `authority_granted` always false | pass |
| Trust | Scanner never upgrades trusted_* | pass |
| Observatory | `agent.injection_assessment` on timeline | pass |
| Corpus | high fixture detects; benign clean | pass |
| ADR-0026 | accepted | pass |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `6cc8264` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V6_T06_SMOKE_OK` |
