---
id: ADR-0035
title: Keep DEEPER_EVAL recursive-policy bake-off out of ACP production
status: proposed
date: 2026-08-18
owners:
  - platform
scope:
  globs:
    - "../maintenance-evals/src/maintenance_evals/recursive_policy.py"
    - "../maintenance-evals/scripts/run_recursive_policy_stage_a.py"
    - "src/agent_control/eval_arm_context.py"
    - "config/recursive_context.yaml"
  symbols:
    - decide_recursive_context
    - run_second_stage
    - decide_p1
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-11-18
agent_visibility:
  - review
  - developer
---

# Context

Sealed H1 (v2 ARB) never invoked C0/C1 because eval-dispatch calls
`decide_recursive_context` with zeros for memory/root-cause counts. Frozen C0
tools also query CT103 backends rather than the eval workspace. A non-scored
DEEPER_EVAL bake-off (`1.7.0-deeper-eval-recursive-policy-nonscored`) measured
bounded second-stage exploration (rg + import neighbors, not RLM) on ARB DEV
43. Stage A gated `INSUFFICIENT_SIGNAL` (`P+_yield_pos=0/43`). Stage B is not
authorized. ADR-0016 and ADR-0034 remain the production/eval-dispatch
recursive policies.

# Decision

P1/P+ live only in `maintenance-evals`. Do not copy them into
`decide_recursive_context`, `recursive_context.yaml`, the recursive worker, or
`eval_arm_context` on the basis of Stage A. Do not treat Stage A as an H1 or
H3 result. A later ACP change needs a new ADR after a Stage B GO (or a
separately frozen experiment), not this freeze.

# Consequences

Positive: sealed H1 verdicts and reserved `1.6.0-h3-longitudinal-scored` stay
untouched; eval policy can fail closed without rewriting production recursion.
Negative: C0/C1 remain uninvoked on the frozen H1 path; empty workspace FTS is
still unsolved.
Follow-up: do not retune P1 against H1 outcomes; do not run Stage B until a
new defining commit authorizes it.
