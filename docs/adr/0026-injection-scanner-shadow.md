---
id: ADR-0026
title: Prompt-injection scanner stays shadow-only
status: accepted
date: 2026-07-21
owners:
  - platform
scope:
  globs:
    - "src/agent_control/security/injection_scanner.py"
    - "src/agent_control/security/injection_events.py"
    - "src/agent_shared/models/injection_assessment.py"
  symbols:
    - InjectionAssessment
    - assess_text_shadow
    - authority_granted
decision_type: security
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-21
agent_visibility:
  - review
  - developer
---

# Context

V6 needs visible injection risk on untrusted issue/comment content before the V7 bake-off. Blocking on probabilistic scanners is operationally risky (false positives stalling Risk 0/1 work) and must not become an authority channel.

# Decision

1. Emit `injection_assessment.v1` in **shadow mode only** (`mode=shadow`, `authority_granted=false` always).
2. Modular detectors (LlamaFirewall-style) may recommend `flag` / `exclude`; they never grant trust or mutate policy authority. Only provenance labels and policy gates authorize actions (ADR-0017 / T01 trust classes).
3. Assessments are durable ledger events (`agent.injection_assessment`) visible in Agent Observatory.
4. Blocking mode requires a new ADR and explicit operator approval.

# Consequences

- High-risk fixtures produce assessments in Observatory without stopping enqueue.
- Operators can tune detectors via corpus FP/FN reports without changing gate semantics.
