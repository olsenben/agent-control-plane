---
id: ADR-0034
title: Apply frozen H1 A/B/C0/C1 context inside eval-dispatch
status: proposed
date: 2026-08-16
owners:
  - platform
scope:
  globs:
    - "src/agent_control/eval_dispatch.py"
    - "src/agent_control/eval_arm_context.py"
  symbols:
    - apply_arm_context
    - write_arb_trajectory
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-11-16
agent_visibility:
  - review
  - developer
---

# Context

Wave A added `agentctl eval dispatch` so maintenance-evals can run a real
platform agent. The first implementation labeled arms in telemetry but did not
apply A/B/C0/C1 context. A scored H1 batch on that path would compare four
labels of the same policy and invalidate the hypothesis.

ADR-0011 already defined deterministic CT103 preflight. ADR-0016 already
defined conditional recursive context. Those policies were not wired into the
eval-only workspace path (no Gitea, no Redis webhook).

# Decision

`eval_dispatch` applies the frozen H1 arm to the exact-SHA workspace before
the engine runs:

- A `local-direct`: no pack, no recursive worker
- B `local-deterministic`: workspace FTS/rg plus path extract into a context pack
- C0 `local-recursive-fallback`: B plus `decide_recursive_context` (no force)
- C1 `local-recursive-2070`: C0 plus the model controller; invoked runs that
  report gpt-4o-mini / OpenAI / non-gpu / non-`qwen2.5-coder:7b` are harness
  contamination

Retrieval evaluation uses inspect / read-only scope and writes an
`arb_trajectory.jsonl` for the official `eval-trajectories` binding.
Placeholder verifier commands stay in the harness, not the ACP container.

# Consequences

Positive: scored Wave D can claim arm differences on the platform path.
Negative: local FTS is a workspace approximation of CT103 graph preflight;
missing graph edges are path-extract misses, not Orbit edges. Recursive
trigger rates may be lower than production Gitea sessions.
Follow-up: Wave E freezes the H1 winner; this ADR does not select a winner.
