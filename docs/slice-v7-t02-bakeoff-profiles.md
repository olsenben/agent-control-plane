# Slice V7 T02 — Bake-off profiles A–D

**Status:** Done — deploy verify PASS tip `234e248` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T02  
**Deps:** T01  

## Goal

Four named controller / context strategy ablation profiles (A–D), each runnable against the **same** verified `eval_bundle.v1` fixture without mutating production memory.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Config | Profiles A–D defined with distinct strategies / bounds | pass |
| Selectable | Single profile or all four via CLI | pass (`--profile` / `all`) |
| Same fixture | All four share identical `source_eval_bundle_sha256` | pass |
| Safety | No repo write, no network, no unbounded recursion, shadow ≠ authority | pass |
| Namespace | Distinct `bakeoff/profile-{X}/…` namespaces per profile | pass |

## Implementation

- `config/bakeoff_profiles.yaml` — A deterministic / B bounded RLM / C graph-memory heavy / D experimental recurrent
- `src/agent_control/bakeoff_profiles.py` — load + dry-run → `bakeoff_run.v1`
- CLI: `agentctl eval bakeoff-run --bundle … --profile all|A|B|C|D`

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `234e248` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V7_T02_SMOKE_OK profiles 4` |
| CT103 / CT104 | `234e248` / `234e248` |
