---
id: ADR-0014
title: Adequacy profiles scope verification claims (not universal correctness)
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "config/adequacy_profiles.yaml"
    - "src/agent_control/session/adequacy.py"
    - "src/agent_shared/models/adequacy.py"
    - "src/agent_shared/models/verification_claim.py"
    - "src/agent_control/session/verification.py"
  symbols:
    - evaluate_adequacy
    - VerificationClaim
    - AdequacyEvaluation
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

ADR-0012 records machine verification events, but a bare `status=passed` can be read as universal correctness. V4 §0.5 requires scoped claims and an adequacy/acceptance profile before `fixed_verified`. Agent-authored tests must not silently inflate verification.

# Decision

1. Ship `config/adequacy_profiles.yaml` with command-mapped profiles (`risk0_read_only`, `risk1_hypothesis`, `risk2_fix_ci`).
2. Extend `verification_claim.v1` with adequacy fields and explicit scope (`scope_behavior`, `scope_files`).
3. CT103 evaluates the profile when stamping claims. CT102 aggregate-only evidence yields `ci_regression_passed` with `fixed_verified=false` unless agent-authored tests are independently attested.
4. Comments and CLI expose adequacy outcome; narrative alone cannot set `fixed_verified`.

# Consequences

- Positive: operators see scoped outcomes; agent tests are honest limitations by default.
- Negative: most live fix verifies will show `ci_regression_passed` until agent-test attestation is wired.
- Follow-up: extract changed test paths from patch bundles into evaluation inputs.

# Related

- [slice-t04-adequacy-profile.md](../slice-t04-adequacy-profile.md)
- ADR-0012, ADR-0001
