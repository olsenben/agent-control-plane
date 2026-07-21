# Slice V6 T07 — NL invocation and clarification lifecycle

**Status:** Done — deploy verify PASS tip `70de9a3` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T07  
**Deps:** T05, T06 Done  

## Goal

Pre-session `invocation_id` FSM for `@agent` NL; deterministic `/agent` unchanged; Instructor optional; Semantic Router gated off.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| `/agent review` | Unchanged dispatch | pass |
| `@agent explain why CI fails` | Resolves to explain | pass |
| No `@agent` / `/agent` | No dispatch | pass |
| Ambiguous NL | clarification_requested via invocation_id | pass |
| Semantic Router | Not mandatory day one | pass |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `70de9a3` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V6_T07_SMOKE_OK` |
