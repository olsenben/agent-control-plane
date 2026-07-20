# Slice V5 T03 — Review replay console

**Status:** In Progress  
**Date:** 2026-07-20  
**Epic ticket:** T03  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0023-review-replay-console.md](adr/0023-review-replay-console.md)

## Goal

Operator can replay one finished `/agent review` session end-to-end from durable CT103 artifacts along the spine **issue → context → model → policy → memory**.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Stages | Replay document includes ordered stages issue/context/model/policy/memory | pending |
| Finished gate | Default CLI requires `session.status=finished` | pending |
| Artifacts | Context stage loads durable `memory_preflight` + `context_packet` when present | pending |
| Memory | Memory stage surfaces selective writeback record / `agent.memory_*` events | pending |
| Smoke | CT103 `agentctl replay review` on a finished review session returns `complete=true` | pending |

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

## Deploy verification

_(filled after CT103/CT104 tip pin)_
