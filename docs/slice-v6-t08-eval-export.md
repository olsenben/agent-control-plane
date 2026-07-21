# Slice V6 T08 — Frozen eval export and V7 handoff

**Status:** Done — deploy verify PASS tip `a9917b8` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T08  
**Deps:** T03–T07  

## Goal

Content-addressed `eval_bundle.v1` via `agentctl eval export`; production memory untouched; V7 preview ledger.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Export | `eval_bundle_sha256` verifies | pass |
| Timeline | Reproduces observation events | pass |
| Memory | `production_memory_touched=false` | pass |
| V7 preview | `boss-ledger-v7-preview.md` | pass |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `a9917b8` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V6_T08_SMOKE_OK` |
