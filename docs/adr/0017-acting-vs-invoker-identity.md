---
id: ADR-0017
title: Split acting_identity from human invoked_by
status: proposed
date: 2026-07-20
owners:
  - platform
scope:
  globs:
    - "src/agent_control/invocation_ack.py"
    - "src/agent_control/gitea_comments.py"
    - "src/agent_control/workflows/dispatch.py"
    - "src/agent_shared/models/agent_session.py"
  symbols:
    - IdentityAudit
    - format_invocation_started
    - acting_identity
    - invoked_by
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

Gitea comments and publishes are authenticated with `GITEA_BOT_TOKEN` on CT103, but sessions and comments historically blurred who *acted* versus who *invoked* `/agent …`. Humans filtering bot traffic and auditing approvals need a clear split. Silent runs (no started/terminal comments) also made correlation by `run_id` unreliable.

# Decision

1. **Acting identity** is the bot principal (`GITEA_ACTING_IDENTITY`, default `agent-bot`) that owns `GITEA_BOT_TOKEN` on CT103 only. Bot posts must never be attributed as the human invoker.
2. **Invoker** is the human webhook author (login + optional user id + source comment/delivery), recorded on `AgentSession`, `agent.session_started`, and comment footers as `invoked_by` / `invoked_by_id` / `source_*`.
3. **Ack protocol:** every accepted enqueue posts a started comment; terminal success/failure/blocked paths post (or extend) a comment with the same `run_id`. Approvals stay bound to the human invoker/approver, not the bot.

# Consequences

- Sessions and Gitea footers carry explicit dual-identity fields (T10).
- Ops must keep `GITEA_BOT_TOKEN` as a dedicated bot user PAT (never a human personal PAT; never on CT104) — continues ADR-0004.
- Merge/deploy of T10 waits for deploy-verify owner (identity lane does not tip-pin).
