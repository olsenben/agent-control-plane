# Slice T09 — Non-demo 6F.2 staged expand (ACP allowlist only)

**Status:** Implemented — awaiting deploy verify  
**Date:** 2026-07-20  
**Epic ticket:** T09  
**Builds on:** ADR-0009, [slice-v411-closeout.md](slice-v411-closeout.md), [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md)

## Goal

Close the epic ticket for non-demo 6F.2: durable proof that CT103 runs

```text
Observe → repair-no-publish → one-class publish on ACP
```

without widening beyond `ai-sdlc-lab/agent-control-plane` + `lint_failure`. No new ADR (scope not widened).

## Acceptance

| Check | Expected |
|-------|----------|
| `agentctl repair stage-status` | `t09_complete=true` on live CT103 |
| Allowlist | Exact ACP only (no wildcards) |
| Class fence | `lint_failure` only; `test_failure` / demo-app denied |
| Publish stage | Flag on ⇒ ACP lint publish allowed; off ⇒ `repair_publish_disabled` |
| Demo heuristic | Never applies to ACP |

## Artifacts

| Path | Role |
|------|------|
| `src/agent_control/ci/repair_stages.py` | Stage status reporter |
| `agentctl repair stage-status` | Operator smoke |
| `tests/test_repair_stages_t09.py` | Unit coverage |

## Follow-on

- T13 patch tournaments (flag-gated; after this tip green)
