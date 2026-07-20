# Coordinator handoff 003

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 003 |
| Date (UTC) | 2026-07-20 |
| Slice / ticket ID | T01 AgentFacts-lite |
| Tip SHA (ACP) | `bdbdc99` |
| Epic | V5 governance & transparency |
| `stopped_reason` | `group_boundary_stop` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-003.md
tickets_done: 1 / 6
next_ticket_id: T02
blocker: none
stopped_reason: group_boundary_stop
tip_sha: bdbdc99
```

## Slice outcome

- Goal completed (one sentence): AgentFacts-lite manifest + MD↔JSON sync; unsigned/stale fails `agentctl agentfacts check`.
- Slice doc path: `docs/slice-v5-t01-agentfacts-lite.md`
- Deploy verify path / status: `pass` (in slice doc)
- CT103 tip / CT104 tip: `bdbdc99` / `bdbdc99`

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: _(none)_
- Actions run IDs: 705, 706, 707
- Session / run IDs: unit `tests/test_agentfacts_t01.py`; live unsigned negative on CT103
- ADR IDs: ADR-0020

## Decisions the next coordinator must honor

1. Do not start T03/T04 until T01 remains Done; T02 deps = T01 only.
2. Re-run `agentctl agentfacts sign` after any AGENT_CARD.md / agent-card.json edit; keep Dockerfile COPY of those three artifacts.
3. Memory-as-governance (T02) should emit audit events; do not weaken AgentFacts check.

## Next coordinator: first actions

1. Orient from `docs/handoff/boss-ledger-v5.md` — Next = T02 Memory-as-governance.
2. Create `docs/slice-v5-t02-*.md`; implement fix-path deny on repeated_failed_fix without new evidence.
3. Deploy-verify before marking T02 Done.

## Open risks (one line each)

- Content-hash integrity alone does not stop a committer who rewrites cards + manifest together; HMAC remains optional.
