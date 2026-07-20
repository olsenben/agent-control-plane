---
id: ADR-0018
title: Bounded recursive Qwen loop with CI-grounded evidence selection
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/qwen_loop/**"
    - "config/recursive_qwen_loop.yaml"
    - "src/agent_shared/models/qwen_loop.py"
    - "src/agent_control/ci/observe.py"
    - "docs/slice-t08-recursive-qwen-loop.md"
  symbols:
    - evaluate_ci_grounded_retry
    - select_evidence_context
    - QwenLoopResult
    - record_ci_grounded_qwen_loop
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-08-20
agent_visibility:
  - review
  - developer
---

# Context

T07 ships conditional recursive context for dispatch. V4 impl order item 9 requires a Recursive Qwen loop that revises after CI failure using evidence-selected context, with hard stop conditions — not an unbounded self-critique loop. T09 separately owns non-demo 6F.2 allowlist expansion.

# Decision

1. Ship `qwen_loop_result.v1` plus `config/recursive_qwen_loop.yaml` with finite `max_ci_repair_iterations` (default 3).
2. On CI `failing`/`verified`, CT103 records a loop decision via `record_ci_grounded_qwen_loop` (observe hook). Evidence preference: CI failure evidence → recursive_context refs → preflight citations.
3. `action=retry` only when failing, under budget, and evidence is usable. Always set `bounded=true` / `unbounded_forbidden=true`.
4. Loop decision does **not** enqueue repair or expand allowlists; T09 remains the gate for sandboxed repair dispatch.

# Consequences

- Positive: CI-grounded retries have an explicit, testable bound and selected context packet for the next Qwen pass.
- Negative: retry intent is advisory until a consumer (fix re-dispatch / T09) acts on it.
- Follow-up: T09 repair allowlist; T13 tournaments after T08 Done.

# Related

- [slice-t08-recursive-qwen-loop.md](../slice-t08-recursive-qwen-loop.md)
- ADR-0016 (conditional recursive context)
- ADR-0012 (verification evidence gate)
