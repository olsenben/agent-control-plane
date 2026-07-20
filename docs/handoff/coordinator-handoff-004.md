# Coordinator handoff 004

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 004 |
| Date (UTC) | 2026-07-20 |
| Slice / ticket ID | T02 Memory-as-governance |
| Tip SHA (ACP) | `f2b8ce9` |
| Epic | V5 governance & transparency |
| `stopped_reason` | `group_boundary_stop` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-004.md
tickets_done: 2 / 6
next_ticket_id: T03
blocker: none
stopped_reason: group_boundary_stop
tip_sha: f2b8ce9
```

## Slice outcome

- Goal completed (one sentence): Fix path denies when memory shows repeated failure class without new evidence; audit event emitted.
- Slice doc path: `docs/slice-v5-t02-memory-as-governance.md`
- Deploy verify path / status: `pass` (in slice doc)
- CT103 tip / CT104 tip: `f2b8ce9` / `f2b8ce9`

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: _(none)_
- Actions run IDs: 711, 712, 713
- Session / run IDs: unit `tests/test_memory_governance_t02.py`; live smoke issue `99002` / `T02_DENY_OK` + `T02_AUDIT_OK`
- ADR IDs: ADR-0021

## Decisions the next coordinator must honor

1. Do not start T05/T06 until their deps are Done; T03 and T04 may proceed in parallel after T01 (both Todo; T01 Done).
2. Memory governance threshold defaults to 2; unlocks via `new_evidence=true` or newer review/plan findings — do not weaken AgentFacts check.
3. Failed-fix memory writeback is distinct from 6E.2 `ci_verified`; keep that separation.

## Next coordinator: first actions

1. Orient from `docs/handoff/boss-ledger-v5.md` — Next = T03 Review replay console (or T04 if dual-lane).
2. Create `docs/slice-v5-t03-*.md` (or T04); implement replay of one finished review session from durable artifacts.
3. Deploy-verify before marking Done.

## Open risks (one line each)

- Threshold/heuristic may false-deny thrashy but legitimate retries until operator adds new evidence.
