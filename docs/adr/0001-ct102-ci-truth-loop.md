---
id: ADR-0001
title: CT102 CI aggregate truth before fix memory
status: proposed
date: 2026-07-14
owners:
  - platform
scope:
  globs:
    - "src/agent_control/ci/**"
    - "src/agent_shared/models/ci.py"
    - "src/agent_control/jobs/state.py"
    - "src/agent_control/results_ingest.py"
    - "src/agent_control/gitea_client.py"
  symbols:
    - CiVerificationResult
    - PendingCiRecord
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-14
agent_visibility:
  - review
  - developer
---

# Context

Slice 6D opens an agent PR and stops at `pr_opened_pending_ci`. Fix success must not be model or PR-open confidence — CT102 (Gitea Actions) is the verification plane. Webhooks alone are not trustworthy enough to drive memory writeback.

# Decision

1. **Signal vs authority:** `workflow_run` webhooks notify CT103; Gitea Actions API confirms state. If they disagree, trust the API.
2. **Correlation:** Pending fixes are keyed by `repository` + exact `head_commit_sha` from 6D. Wrong SHA or wrong repo does not correlate.
3. **Aggregate verdict:** Reducer requires every required workflow (CI matrix / `FIX_CI_REPO_DEFAULT_WORKFLOW`) to succeed for that exact SHA before `verdict=verified`. Never treat “any green workflow” as success.
4. **Append-only events:** Historical `agent.run_completed` stays immutable; later `agent.fix_ci_observed` / `agent.fix_ci_verdict_changed` append.
5. **Memory gate (6E.2):** Upsert fix memory only when verdict=`verified`, with `memory_quality=ci_verified`.
6. **Feature flag:** Off by default (`FIX_CI_OBSERVE_ENABLED=false`); enable on CT103 after 6D sign-off.

# Consequences

- Positive: Fail-closed CI truth; reruns can recover `failing → verified`; reconciliation covers dropped webhooks.
- Negative: Extra API load; empty required matrix stays `pending` (or uses repo default) rather than green-washing.
- Follow-up: Homelab sign-off on a live agent PR; re-validate Gitea 1.26 webhook field names against production deliveries.
