# Slice 5.4a — CT103-authoritative typed sessions

**Status:** Implemented (acceptance pending homelab fake review)  
**Date:** 2026-07-19  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md)

## Goal

Every `/agent review|plan|fix|repair` creates a durable `agent_session.v1` on CT103 with append-only `agent.session_*` ledger events. CT104 echoes `session_id` in evidence only; correlation fields are CT103-derived.

## Session identity

- New user command → new `sess-…` (always distinct from `run-…`).
- Retry / auto-repair → same session, additional `run_id` via run→session index.
- Separate `/agent repair` → new session.

## Terminal ownership

| Command | Terminal owner |
|---------|----------------|
| review / plan | Results ingest |
| fix / repair | Publish/verification |
| Enqueue failure | Dispatch → `failed` |
| Policy denial | Dispatch/approval → `blocked` |

## Storage

- `agent-state/projects/{owner}/{repo}/sessions/{session_id}.json`
- Index: `sessions/by_run_id/{run_id}.json`

## Ledger spine

`agent.session_started` → `agent.subject_context_resolved` → (`agent.session_worker_event` allowlisted) → `agent.session_finished` | `failed` | `blocked`

## `input_state_sha`

Canonical JSON (`input_state.v1`): `project`, `subject_kind`, `subject_number`, `command_kind`, `head_sha` (dispatch SHA), `policy_source_sha`. SHA-256 of `json.dumps(..., sort_keys=True, separators=(",", ":"))`.

## CLI

```text
agentctl session show --session-id sess-… --repo owner/repo [--json]
agentctl session list --repo owner/repo [--command-kind review] [--json]
```

## Worker mismatch

Worker-supplied `session_id` that disagrees with the CT103 run index → fail closed: no mapped session event, session not finalized, inbox left unprocessed.

## Tests

`tests/test_typed_sessions.py`, extended `tests/test_fake_review_run.py`.

## Out of scope (5.4b+)

Failure taxonomy expansion, preflight, verification gate, selective writeback, Gitea ack comments, 2070.
