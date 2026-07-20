# Slice V5 T03 — Review replay console

**Status:** Done — deploy verify PASS tip `5ca8d78` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T03  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0023-review-replay-console.md](adr/0023-review-replay-console.md)  
**Feature tip:** `b7fa044` (included in combined dual-lane tip `5ca8d78`)

## Goal

Operator can replay one finished `/agent review` session end-to-end from durable CT103 artifacts along the spine **issue → context → model → policy → memory**.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Stages | Replay document includes ordered stages issue/context/model/policy/memory | pass (unit + CT103) |
| Finished gate | Default CLI requires `session.status=finished` | pass (unit) |
| Artifacts | Context stage loads durable `memory_preflight` + `context_packet` when present | pass (unit + CT103) |
| Memory | Memory stage surfaces selective writeback record / `agent.memory_*` events | pass (unit + CT103) |
| Smoke | CT103 `agentctl replay review` on a finished review session returns `complete=true` | pass `T03_REPLAY_OK` |

## Design

1. Read-only assembler `agent_control.replay.review.build_review_replay`.
2. Resolve session by `--session-id` and/or `--run-id` (run index).
3. Stages pulled from: `agent_session.v1`, session artifact dir, project event ledger, SQLite trajectory memory.
4. CLI: `agentctl replay review --repo owner/name --session-id sess-…` (JSON default; `--text` compact).

## CLI

```bash
agentctl replay review --repo ai-sdlc-lab/demo-app --session-id sess-…
agentctl replay review --repo ai-sdlc-lab/demo-app --run-id run-… --text
```

## Docs

- Operator notes: [replay.md](replay.md)

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T03 |
| Slice doc | `docs/slice-v5-t03-review-replay-console.md` |
| Tip SHA (expected) | `5ca8d78` (includes T03 `b7fa044` + T04 docs) |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator (deploy-verify owner for T03∥T04) |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test | pass | run #723 |
| deploy (CT103) | pass | run #725 |
| deploy-ct104 | pass | run #724 |

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `5ca8d78` | yes |
| CT104 (`192.168.4.63`) | `5ca8d78` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model paths); redis/state ok |
| Required compose services up | ok | control-plane running tip |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Seed finished review + durable artifacts | pass | `T03_SEED_OK` `sess-9de43b40…` / `run-t03-replay-smoke` |
| `agentctl replay review` complete=true | pass | `T03_REPLAY_OK` stages issue→context→model→policy→memory |
| Dual-lane T04 drift on same tip | pass | `T04_DRIFT_OK missing=2` |
| `agentctl agentfacts check` | pass | ok; T03 limitation listed |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | pass / N/A (unchanged) |
| Risk 2 still gated | pass / N/A (review Risk 1) |

```text
DEPLOY_VERIFY: PASS
tip: 5ca8d78
next_slice_unblocked: yes
blocker: none
```
