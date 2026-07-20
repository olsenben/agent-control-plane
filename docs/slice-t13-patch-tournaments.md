# Slice T13 — Patch tournaments / rewards (experiment flag)

**Status:** Done — deploy verify PASS tip `078d030` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T13  
**Deps:** T08 Done; T09 Done  
**ADR:** [0019-flag-gated-patch-tournaments.md](adr/0019-flag-gated-patch-tournaments.md)

## Goal

Ship flag-gated patch tournaments + reward logging. Defaults **OFF** (`config/experiments.yaml`).

## Acceptance

| Check | Expected |
|-------|----------|
| Flag off | `spawn` / `rewards log` → `denied` / `*_disabled` |
| Flag on (test) | Spawn N≤4 candidates; judge only CI passers; all-fail → no winner |
| Rewards | JSONL under agent-state; deterministic score_fn; summarize |

## Deploy verification (2026-07-20)

| Host | Tip | Notes |
|------|-----|-------|
| CT103 / CT104 | `078d030` | Actions success ×3; `DEPLOY_TIP_READY` |
| Smoke | `agentctl tournament spawn` | `denied` / `patch_tournament_disabled` |
| Smoke | `agentctl rewards log` | `denied` / `rl_reward_logging_disabled` |
| Config | `experiments.yaml` in image | both flags `false` |

## CLI

```bash
agentctl tournament spawn --finding-id F-1
agentctl tournament judge --tournament-id tourn-…
agentctl rewards log --run-id run-… --outcome ci_passed
agentctl rewards summarize
```

## Policy

- No default enable in `.env` / compose
- Does not expand 6F.2 repair allowlist
- No auto branch push / PR in v1 (reserved branch names only)
