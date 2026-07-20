# Slice T08 — Recursive Qwen loop (evidence + CI retries)

**Status:** Done — deploy verified — PR pending merge / deploy-verify owner  
**Date:** 2026-07-20  
**Epic ticket:** T08  
**Plan:** V4 impl order item 9 / recursive inference goal (§0.4)  
**Builds on:** [slice-8c-recursive-context.md](slice-8c-recursive-context.md) (T07), [slice-5.6-verification-evidence-gate.md](slice-5.6-verification-evidence-gate.md) (T01), [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) (6F.1 evidence)  
**ADR:** [0018-bounded-recursive-qwen-loop.md](adr/0018-bounded-recursive-qwen-loop.md)

## Goal

After CT102 CI fails, select evidence-focused context (CI failure evidence + optional T07 recursive_context) and decide whether another Qwen pass is allowed under a **finite** budget. Never unbounded. Does **not** expand the 6F.2 repair allowlist (T09).

## Acceptance (ledger smoke)

| Check | Expected |
|-------|----------|
| CI failing + collected evidence + attempt < max | `action=retry`, selected `evidence_refs` non-empty |
| attempt >= `max_ci_repair_iterations` | `action=stop`, `stop_reason=budget_exhausted` |
| CI verified | `action=stop`, `stop_reason=verification_passed` |
| Loop invariant | `bounded=true`, `unbounded_forbidden=true`; simulator always terminates |
| Repair allowlist | unchanged — notes include `does_not_enable_6f2_repair_allowlist` |

## Artifacts

| Artifact | Path |
|----------|------|
| Config | `config/recursive_qwen_loop.yaml` |
| Models | `src/agent_shared/models/qwen_loop.py` (`qwen_loop_result.v1`) |
| Loop | `src/agent_control/qwen_loop/loop.py` |
| Evidence select | `src/agent_control/qwen_loop/evidence.py` |
| Observe hook | `src/agent_control/qwen_loop/observe_hook.py` (wired from `ci/observe.py`) |
| Session file | `sessions/{id}/qwen_loop_result.json` |
| Session ref | `AgentSession.qwen_loop` |
| Tests | `tests/test_qwen_loop_t08.py` |

## Policy

- `max_ci_repair_iterations` default 3 (also plan/patch caps in config)
- Retry requires usable evidence when `require_evidence_for_retry=true`
- Stop on verification_passed / budget_exhausted / insufficient_evidence / contradictory_evidence / human_required / disabled
- External feedback required: CI evidence + memory/graph citations — not model self-confidence
- T09 owns sandboxed repair dispatch / allowlist expansion

## Tests

```bash
.venv/bin/pytest tests/test_qwen_loop_t08.py -q
.venv/bin/ruff check .
```

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T08 |
| Tip SHA | `3243cbf` |
| PR | [#29](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/29) |
| Verdict | **DEPLOY_VERIFY: PASS** |

## Follow-on

- T09 Risk-2 repair allowlist (consumes retry intent separately)
- T13 patch tournaments (depends on T08 Done)
