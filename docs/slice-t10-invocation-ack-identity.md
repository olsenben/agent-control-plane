# Slice T10 — Invocation Ack + Acting vs Invoker Identity

**Status:** Done — deploy verified (PR pending merge; deploy-verify owned by boss)  
**Date:** 2026-07-20  
**Epic ticket:** T10  
**Plan:** V4 deferred — “invocation ack UX + acting vs invoker identity”  
**Lane:** Identity (`epic/lane-identity-t10`) — no CT103/CT104 tip pin from this lane

## Goal

No silent `/agent` runs. Every accepted command posts a **started** Gitea comment; every terminal outcome posts a **success / failure / blocked** comment with the **same `run_id`**. Bot posts are labeled as `acting_identity` (`agent-bot`); the human who invoked is `invoked_by` only.

## Protocol

```text
accepted / queued  →  started ack (run_id, command, invoker, queue/host)
finished           →  success | failure | blocked (same run_id + identity footer)
```

| Path | Started | Terminal |
|------|---------|----------|
| review / plan (typed enqueue) | `format_invocation_started` after Redis enqueue | ingest summary + identity footer |
| inspect / explain | same started ack | ingest summary + identity footer |
| fix (authorized enqueue) | `format_fix_started` (+ identity footer) | failed-fix ingest / publish / CI comments (existing) |
| fix policy deny / empty scope | — | `format_fix_blocked` with `run_id` + identity |
| enqueue / preflight failure | — | terminal failure comment (`enqueue_failed` / `preflight_failed`) |

## Identity split

| Field | Meaning |
|-------|---------|
| `acting_identity` | Bot principal (`GITEA_ACTING_IDENTITY`, default `agent-bot`) owning `GITEA_BOT_TOKEN` on CT103 |
| `invoked_by` | Human Gitea login |
| `invoked_by_id` | Human numeric user id (when present on webhook) |
| `source_comment_id` | Invoking comment id |
| `source_delivery_id` | Webhook delivery id |

Approvals remain bound to the **human** invoker/approver, not the bot.

## Artifacts

| Artifact | Path |
|----------|------|
| Formatters | `src/agent_control/invocation_ack.py` |
| Session fields | `agent_shared.models.agent_session.AgentSession` |
| Trigger `author_id` | `TriggerContext` + `build_trigger_context` |
| Config | `GITEA_ACTING_IDENTITY` (default `agent-bot`) |
| Tests | `tests/test_invocation_ack_t10.py` |

## Tests

```bash
.venv/bin/pytest tests/test_invocation_ack_t10.py tests/test_gitea_comments.py -q
.venv/bin/ruff check .
```

## Deploy smoke (owner)

After merge + tip pin: start + terminal comments on a live issue; session JSON shows `acting_identity` ≠ `invoked_by`.

## Follow-on

- Ops: confirm CT103 `GITEA_BOT_TOKEN` is the dedicated `agent-bot` user (not a human PAT)
- Optional: enrich CI / publish comments with full invoker when session is loaded

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T10 |
| Tip SHA | `4a9acdc` |
| PR | [#26](https://git.ham-sup-lo.com/ai-sdlc-lab/agent-control-plane/pulls/26) |
| Verdict | **DEPLOY_VERIFY: PASS** |
| ADR | ADR-0017 (after Orbit 0015 / RLM 0016) |
