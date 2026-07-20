---
id: ADR-0016
title: Conditional recursive context worker on 2070 with fail-soft skip
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/recursive_context/**"
    - "config/recursive_context.yaml"
    - "src/agent_control/session/prepare_dispatch.py"
    - "docs/slice-8c-recursive-context.md"
  symbols:
    - run_conditional_recursive_context
    - RecursiveContextResult
    - ReadOnlyToolBelt
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

Slice 5.5a records `recursive_context_required` as advisory without invoking a controller. V4 Phase 20 requires a bounded, read-only RLM-style worker on the 2070 only when preflight detects context pressure — never as policy or write authority.

# Decision

1. Ship `recursive_context_result.v1` plus `config/recursive_context.yaml` budgets and allowlisted tools.
2. Invoke `run_conditional_recursive_context` from prepare **only when** `recursive_context_required=true` (lazy import). False path skips 2070 and does not import the module.
3. Tool belt is read-only; forbidden capabilities hard-deny. `call_primary_model` requires evidence refs; missing live 2070 falls back to deterministic tool results.
4. Persist result + JSONL trajectory under the session directory; failures are fail-soft (do not block enqueue).

# Consequences

- Positive: dispatch gains deeper evidence only when needed; skip path preserves 5.5a latency/safety.
- Negative: first 8c controller is plan-driven deterministic + optional model hook — bake-off (8d) may replace the planner.
- Follow-up: T08 recursive Qwen loop; optional live 2070 health gate metrics.

# Related

- [slice-8c-recursive-context.md](../slice-8c-recursive-context.md)
- ADR-0011 (deterministic preflight)
