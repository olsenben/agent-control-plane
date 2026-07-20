# Slice T07 / 8c — Conditional 2070 recursive context worker

**Status:** Done — deploy verified  
**Date:** 2026-07-20  
**Epic ticket:** T07  
**Plan:** V4 Phase 20 / impl order item 8c  
**Builds on:** [slice-5.5-deterministic-preflight.md](slice-5.5-deterministic-preflight.md), [slice-8b-preflight-graph-coverage.md](slice-8b-preflight-graph-coverage.md)  
**ADR:** [0016-conditional-recursive-context-worker.md](adr/0016-conditional-recursive-context-worker.md)

## Goal

After deterministic preflight, invoke a bounded read-only recursive context worker only when `recursive_context_required=true`. Produce `recursive_context_result.v1` with evidence citations and budget accounting. False path skips 2070 entirely (no module import / no model client).

## Acceptance (ledger smoke)

| Check | Expected |
|-------|----------|
| `recursive_context_required=false` | Result `skipped=true`, `stop_reason=deterministic_preflight_sufficient`, no tool/model calls |
| `recursive_context_required=true` | Durable `recursive_context_result.v1` with `invoked=true`, evidence_refs, trajectory JSONL |
| Authority | `allow_repo_write/network/secret_paths=false`; forbidden tools denied |
| Prepare path | Lazy-import only when required; false path keeps 5.5a no-2070 invariant |

## Artifacts

| Artifact | Path |
|----------|------|
| Config | `config/recursive_context.yaml` |
| Worker | `src/agent_control/recursive_context/worker.py` |
| Tools | `src/agent_control/recursive_context/tools.py` |
| Model | `src/agent_shared/models/recursive_context.py` |
| Session file | `sessions/{id}/recursive_context_result.json` + `recursive_context_trajectory.jsonl` |
| CLI | `agentctl rlm inspect`, `agentctl rlm run` |
| Tests | `tests/test_recursive_context_8c.py` |

## Policy (Phase 20)

- Allowed tools only (search_events, find_*, get_adr_facts, get_memory_by_cause, compare_hypotheses, call_primary_model, …)
- Budgets: depth/subcalls/graph/memory/wall/tokens/output
- Require evidence citations on compare/model conclusions
- No repo/state writes, no policy/verification authority
- Fallback: deterministic tool plan when no live 2070 client (`controller_mode=fallback_deterministic`)

## Tests

```bash
.venv/bin/pytest tests/test_recursive_context_8c.py tests/test_memory_preflight.py -q
```

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T07 |
| Tip SHA | `ee2367b` (merge `91b8d00` + budget/pydantic fixes) |
| PR | [#27](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/27) |
| Verdict | **DEPLOY_VERIFY: PASS** |

| Check | Result |
|-------|--------|
| CT102 Actions | pass on tip `ee2367b` |
| CT103 / CT104 tip | `ee2367b` |
| Live | `SCHEMA=recursive_context_result.v1`; `agentctl rlm` present |
| Unit | `tests/test_recursive_context_8c.py` 7 passed |

## Follow-on

- T08 recursive Qwen loop; T12 controller bake-off (optional)
