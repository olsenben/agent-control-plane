# Handoff template

Copy to `docs/handoff/coordinator-handoff-NNN.md` (boss assigns NNN).  
No transcripts, diffs, or full logs. Decisions only.

---

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | NNN |
| Date (UTC) | |
| Slice / ticket ID | |
| Tip SHA (ACP) | |
| Epic | V4 full build |
| `stopped_reason` | `epic_complete` \| `context_handoff` \| `group_boundary_stop` \| `blocker` \| `deploy_gate_pending` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-NNN.md
tickets_done: N / TOTAL
next_ticket_id: Txx or EPIC_COMPLETE
blocker: none | one line
stopped_reason: …
```

## Slice outcome

- Goal completed (one sentence):
- Slice doc path:
- Deploy verify path / status: `pass` | `fail` | `pending`
- CT103 tip / CT104 tip (must match when slice deploys both):

## Evidence pointers (paths / IDs only)

- Gitea issue / PR:
- Actions run IDs:
- Session / run IDs:
- ADR IDs:

## Decisions the next coordinator must honor

1.
2.
3.

## Next coordinator: first actions

1.
2.
3.

## Open risks (one line each)

-
