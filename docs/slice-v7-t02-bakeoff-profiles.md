# Slice V7 T02 — Bake-off profiles A–D

**Status:** In Progress  
**Date:** 2026-07-21  
**Epic ticket:** T02  
**Deps:** T01  

## Goal

Four named controller / context strategy ablation profiles (A–D), each runnable against the **same** verified `eval_bundle.v1` fixture without mutating production memory.

## Acceptance

| Check | Expected |
|-------|----------|
| Config | Profiles A–D defined with distinct strategies / bounds |
| Selectable | Single profile or all four via CLI |
| Same fixture | All four share identical `source_eval_bundle_sha256` |
| Safety | No repo write, no network, no unbounded recursion, shadow ≠ authority |
| Namespace | Distinct `bakeoff/profile-{X}/…` namespaces per profile |

## Non-goals

- Metrics aggregation (T03)
- Live recursive worker invocation / memory fork-reset (T04)
- Longitudinal report (T05)

## Deploy smoke (minimum)

1. Export or fixture bundle → `agentctl eval bakeoff-run --bundle … --profile all`
2. Four `bakeoff_run.v1` artifacts; identical source SHA; four namespaces
