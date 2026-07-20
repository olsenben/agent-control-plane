---
id: ADR-0019
title: Flag-gated patch tournaments and reward logging default off
status: proposed
date: 2026-07-20
---

# ADR-0019: Flag-gated patch tournaments and reward logging default off

## Context

V4 Phase 21–22 call for home-only patch tournaments and reward logging. Enabling them by default would expand Risk-2 surface and CI load.

## Decision

1. `config/experiments.yaml` holds `experiments.patch_tournament` and `experiments.rl_reward_logging`, both **false** by default.
2. CLI `agentctl tournament` / `agentctl rewards` refuse when flags are off.
3. Tournament v1 records candidate strategies and branch *names* only; no auto-push.
4. Judge selects only among `ci_status=passed`; all-fail → no winner.
5. Rewards append versioned `agent.reward.v1` JSONL under agent-state.

## Consequences

- Positive: research surface available without changing repair allowlist or production defaults.
- Negative: full multi-branch CI orchestration remains a follow-up when flag is explicitly enabled.
- Follow-up: HITL merge of winning branch; optional wiring to T08 evidence packs.
