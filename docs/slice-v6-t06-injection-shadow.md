# Slice V6 T06 — Injection scanner shadow evaluation

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T06  
**Deps:** T01, T03 Done  

## Goal

Shadow-mode modular injection detection (`injection_assessment.v1`) visible in Observatory; never grants authority. Blocking deferred.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Shadow assessment | risk/categories/matched_regions/recommended_action | pending |
| Authority | `authority_granted` always false | pending |
| Trust | Scanner never upgrades trusted_* | pending |
| Observatory | `agent.injection_assessment` on timeline | pending |
| Corpus | high fixture detects; benign clean | pending |
| ADR-0026 | accepted | pending |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | pending |
| Verdict | pending |
| Smoke | `V6_T06_SMOKE_OK` |
