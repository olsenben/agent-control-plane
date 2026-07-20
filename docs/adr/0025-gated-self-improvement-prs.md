---
id: ADR-0025
title: Gated self-improvement proposals land only as Gitea PRs
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/self_improve/**"
    - "src/agent_control/gitea_client.py"
    - "docs/slice-v5-t06-gated-self-improvement.md"
  symbols:
    - propose_self_improve
    - evaluate_in_prod_self_edit
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

Plan §0.4 calls for a gated self-improvement lane: the agent proposes prompt/workflow/tool-schema changes through branch protection + CI — not self-edit in production. V5 T06 is the final governance epic ticket.

# Decision

1. Define **gated path globs** (workflows, `.agent/**`, RLM/`prompts.py`) that may only change via a dedicated propose path.
2. **Deny in-prod self-edit**: refuse writing gated paths into live deploy roots (`/opt/ai-sdlc-lab/agent-control-plane` or `.agent-control-plane-live`).
3. **Propose as PR only** on CT103: create `agent/self-improve-*` branch, Contents API file upsert, `open_or_find_pr` — same write authority model as publish-broker (no CT104 write tokens).
4. `/agent fix` closed-world `always_denied` for workflows stays; this lane does not unlock Risk 2 auto-merge.

# Consequences

- Positive: explicit, auditable channel for agent-authored policy/prompt changes with CI + HITL before merge.
- Negative: Contents API propose is separate from full patch-bundle publish; large multi-file proposals may need a follow-up bundle path.
- Follow-up: optional HITL label / required reviewers on `self-improve` PRs; close or merge smoke PRs as ops policy.

# Related

- [slice-v5-t06-gated-self-improvement.md](../slice-v5-t06-gated-self-improvement.md)
- ADR-0004 (CT103 publish brokerage)
- Closed-world `always_denied` workflows in platform default policy
