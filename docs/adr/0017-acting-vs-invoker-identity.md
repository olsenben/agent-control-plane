---
id: ADR-0017
title: Split acting_identity from human invoked_by
status: accepted
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/invocation_ack.py"
    - "src/agent_control/gitea_comments.py"
    - "src/agent_control/workflows/dispatch.py"
    - "src/agent_control/authorization.py"
    - "src/agent_shared/models/agent_session.py"
    - "src/agent_shared/models/authorization_decision.py"
  symbols:
    - IdentityAudit
    - format_invocation_started
    - acting_identity
    - invoked_by
    - approved_by
    - AuthorizationDecision
decision_type: security
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-20
agent_visibility:
  - review
  - developer
---

# Context

Gitea comments and publishes are authenticated with `GITEA_BOT_TOKEN` on CT103, but sessions and comments historically blurred who *acted* versus who *invoked* `/agent …`. Humans filtering bot traffic and auditing approvals need a clear split. Silent runs (no started/terminal comments) also made correlation by `run_id` unreliable. Authorization was also conflated into a single gate (for example using `approved_by_login` as `invoked_by` on fix enqueue).

# Decision

1. **Acting identity** is the bot principal (`GITEA_ACTING_IDENTITY`, default `agent-bot`) that owns `GITEA_BOT_TOKEN` on CT103 only. Bot posts must never be attributed as the human invoker.
2. **Invoker** is the human webhook author (login + optional user id + source comment/delivery), recorded on `AgentSession`, `agent.session_started`, and comment footers as `invoked_by` / `invoked_by_id` / `source_*`.
3. **Approver** (Risk 2) is recorded separately as `approved_by` when an owner/configured approver grants approval. Invoker and approver may differ (read-only planner + owner approver).
4. **Ack protocol:** every accepted enqueue posts a started comment; terminal success/failure/blocked paths post (or extend) a comment with the same `run_id`. Approvals stay bound to the human invoker/approver, not the bot.
5. **Separate predicates** (`authorization_decision.v1`): invoker check, approver check, acting-identity (bot write) check, policy check, and approval-scope (including source SHA) are evaluated independently — never as one intersection of invoker-write == bot-write. Mutation-critical predicates are rechecked immediately before publish.

# Consequences

- Sessions and Gitea footers carry explicit dual/triple identity fields (T10 + V6 T05).
- Commit trailers include `Invoked-By`, `Agent-Run`, `Agent-Session`, and optional `Approved-By`.
- Ops must keep `GITEA_BOT_TOKEN` as a dedicated bot user PAT (never a human personal PAT; never on CT104) — continues ADR-0004.
- Publish broker fails closed on source-SHA drift or lost bot write between enqueue and publish.
