# Slice V6 T07 — NL invocation and clarification lifecycle

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T07  
**Deps:** T05, T06 Done  

## Goal

Pre-session `invocation_id` FSM for `@agent` NL; deterministic `/agent` unchanged; Instructor optional; Semantic Router gated off.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| `/agent review` | Unchanged dispatch | pending |
| `@agent explain why CI fails` | Resolves to explain | pending |
| No `@agent` / `/agent` | No dispatch | pending |
| Ambiguous NL | clarification_requested via invocation_id | pending |
| Semantic Router | Not mandatory day one | pending |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | pending |
| Smoke | `V6_T07_SMOKE_OK` |
