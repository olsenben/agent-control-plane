---
id: ADR-0036
title: Keep diagnostic memory injection opt-in and off scored H3
status: proposed
date: 2026-08-18
owners:
  - platform
scope:
  globs:
    - "src/agent_control/eval_dispatch.py"
    - "src/agent_control/eval_arm_context.py"
    - "src/agent_workers/rlm/official_engine.py"
    - "../maintenance-evals/src/maintenance_evals/memory_consumption_diagnostic.py"
  symbols:
    - diagnostic_injection
    - assemble_official_engine_prompts
decision_type: architecture
enforcement: hard
risk_level: low
supersedes: []
superseded_by: []
review_after: 2026-11-18
agent_visibility:
  - review
  - developer
---

# Context

Sealed H3 retrieved longitudinal memory but did not place `mem-*` records in
the OfficialRLMEngine messages. A non-scored DEEPER_EVAL diagnostic needs a
wired delivery path without rewriting scored H3 or default scored dispatch.

# Decision

`memory.diagnostic_injection=true` is the only switch that copies caller-supplied
records into `ContextPack.prior_memory` and persists the live official
system/user messages. Default scored / H3 dispatch keeps `diagnostic_injection`
off and still omits records. Admission and retrieval in `memory.py` are
unchanged. This path is not an H3 repair and does not authorize a 2070.

# Consequences

Positive: delivery and citation overlay can be tested on the real official
message builder. Negative: a caller who sets the flag on a scored batch would
change treatment; tests assert the scored driver never passes the flag.
Follow-up: keep the official-smoke result `scored=false` and outside the H3
freeze.
