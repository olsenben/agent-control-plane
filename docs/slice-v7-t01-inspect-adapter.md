# Slice V7 T01 — Inspect AI adapter for eval_bundle.v1

**Status:** Done — deploy verify PASS tip `b1a8a38` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T01  
**Deps:** none (V6 eval export tip `a9917b8` / QA tip `28292c0`)  

## Goal

Provide a framework-neutral → **Inspect AI** adapter that imports a content-addressed `eval_bundle.v1` (from `agentctl eval export`) into Inspect-loadable tasks without touching production memory.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Import | Load a fixture / exported `eval-*.json` into an Inspect task dataset | pass |
| Integrity | Reject or warn if `eval_bundle_sha256` fails verify | pass (fail-closed) |
| Memory | Adapter path sets / respects `memory_namespace`; `production_memory_touched` stays false | pass |
| CLI/docs | Documented entrypoint (module or `agentctl` subcommand) for local bake-off use | pass (`agentctl eval inspect-adapt`) |

## Implementation

- `src/agent_control/inspect_adapter.py` — `load_eval_bundle`, `bundle_to_inspect_task`, `adapt_eval_bundle_file`
- Schema: `inspect_adapt.v1` (samples + bake-off namespace); optional `try_build_inspect_memory_dataset` when `inspect_ai` installed
- CLI: `agentctl eval inspect-adapt --bundle … --out …`

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `b1a8a38` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V7_T01_SMOKE_OK` (CT103); CT103+CT104 tip pin `b1a8a38` |
