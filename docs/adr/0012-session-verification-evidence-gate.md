---
id: ADR-0012
title: Session verification evidence gate (defer fix/repair finish until CI)
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/session/verification.py"
    - "src/agent_shared/models/verification_claim.py"
    - "src/agent_control/ci/observe.py"
    - "src/agent_control/publish/broker.py"
    - "src/agent_control/session/lifecycle.py"
  symbols:
    - request_session_verification
    - apply_ci_verdict_to_session
    - VerificationClaim
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

ADR-0010 said fix/repair finalize at publish/verification, but the implementation finished sessions at publish (`publish_succeeded`) while 6E CI ran asynchronously. V4.1 §0.5 and Slice 5.6 require machine-recorded verification evidence; reasoning alone cannot set verified state. Missing required verification must not look like success.

# Decision

1. CT103 alone emits `agent.verification_requested|passed|failed|missing` with durable `verification_claim.v1` on the session.
2. Successful fix/repair publish does **not** emit `session_finished`. It emits `verification_requested` and leaves the session `running`.
3. Successful fix/repair terminal is `ci_verified` / `repair_ci_verified` only after 6E aggregate verdict `verified` on the exact published commit SHA.
4. Review/plan still finish at ingest, but always emit `verification_missing` (findings/plans are hypotheses; no CI claim).
5. CI `failing` with automatic repair in flight keeps the session nonterminal; otherwise finalize `verification_failed`.
6. CI `expired` → `verification_missing` + `session_blocked`. Superseded pending does not claim passed.

# Consequences

- Positive: session spine matches V4 verification invariant; writeback (5.7) can require evidence refs; comments include scoped Verification blocks.
- Negative: operators must treat post-publish sessions as running until CI; dashboards that assumed finish-at-publish need updating.
- Follow-up: 5.7 selective writeback; adequacy profiles for agent-authored tests.

# Related

- [slice-5.6-verification-evidence-gate.md](../slice-5.6-verification-evidence-gate.md)
- ADR-0010 (typed sessions), ADR-0001 (CT102 CI truth)
