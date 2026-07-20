---
id: ADR-0023
title: Review replay console from durable session artifacts
status: proposed
date: 2026-07-20
---

# ADR-0023: Review replay console from durable session artifacts

## Context

V5 governance needs operator transparency: after a finished `/agent review`, humans must reconstruct what issue, context, model, policy, and memory participated — without re-running the worker or trusting ephemeral CT104 logs.

Typed sessions (ADR-0010), preflight/packet artifacts (ADR-0011), and selective writeback (ADR-0013) already leave durable CT103 state. Missing was a single read-only console that walks that spine end-to-end.

## Decision

1. Add `agent_control.replay.review.build_review_replay` that assembles a `review_replay.v1` document with ordered stages: issue → context → model → policy → memory.
2. Expose `agentctl replay review` (JSON default; optional `--text`). Resolve by `session_id` and/or `run_id`.
3. Default require `session.status=finished` and `command_kind=review`.
4. Sources are CT103-only: session JSON, session artifact dir, project event ledger, SQLite trajectory memory. No remote re-fetch; no mutation.

## Consequences

- Positive: operators can audit one review path from durable artifacts; smoke is a single CLI invocation.
- Negative: completeness depends on prior slices writing preflight/packet/memory; incomplete sessions surface `complete=false` rather than inventing data.
- Follow-up: richer UI / SARIF attach (T05) can consume the same document shape.
