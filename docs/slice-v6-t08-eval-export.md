# Slice V6 T08 — Frozen eval export and V7 handoff

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T08  
**Deps:** T03–T07  

## Goal

Content-addressed `eval_bundle.v1` via `agentctl eval export`; production memory untouched; V7 preview ledger.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Export | `eval_bundle_sha256` verifies | pending |
| Timeline | Reproduces observation events | pending |
| Memory | `production_memory_touched=false` | pending |
| V7 preview | `boss-ledger-v7-preview.md` | pending |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | pending |
| Smoke | `V6_T08_SMOKE_OK` |
