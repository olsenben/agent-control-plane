---
id: ADR-0010
title: CT103-authoritative typed agent sessions
status: proposed
date: 2026-07-19
---

# ADR-0010 — CT103-authoritative typed agent sessions

## Context

Jobs carried `session_id` aliased to `run_id`, and CT104 wrote only local `session_events.jsonl`. V4.1.2 / Slice 5.4 needs a durable, queryable session spine on CT103 for preflight, verification claims, and selective writeback — without trusting worker JSONL for correlation identity.

## Decision

1. **CT103 owns** `agent_session.v1` under `agent-state/.../sessions/` plus `by_run_id` index; persist session + index + `agent.session_started` / `subject_context_resolved` **before** Redis enqueue.
2. **`session_id` (`sess-…`) is always distinct from `run_id` (`run-…`)**; retries and automatic repair append run IDs to the same session.
3. **Correlation fields** (`session_id`, `run_id`, repo, subject, command_kind, risk, `input_state_sha`, dispatch `head_sha`, `correlation_id`) are derived from the CT103 store on ledger events — never from worker claims.
4. **Worker allowlist** is tiny (execution started/result/failed, verification available); mismatch of worker `session_id`/`run_id` → fail closed (no finalize, no mapped event).
5. **Terminal ownership**: review/plan finalize at results-ingest; fix/repair finalize at publish/verification; enqueue failure → `failed`; policy denial → `blocked`.

## Consequences

- Dispatch paths (`maybe_dispatch_rlm_root`, fix enqueue, CI repair) must begin or bind sessions before queueing.
- CT104 continues to echo `session_id` in `agent.run_completed` evidence only.
- CLI: `agentctl session show|list`.
- Follow-ups: 5.4b taxonomy, 5.5 preflight, 5.6 verification gate, 5.7 writeback.

## Related

- [slice-5.4-typed-sessions.md](../slice-5.4-typed-sessions.md), [slice-v412-typed-sessions.md](../slice-v412-typed-sessions.md)
- ADR-0007 (executor ≠ session lifecycle)
