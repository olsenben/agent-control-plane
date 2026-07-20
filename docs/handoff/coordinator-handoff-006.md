# Coordinator handoff 006

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 006 |
| Date (UTC) | 2026-07-20 |
| Slice / ticket ID | T04 Architecture drift detector |
| Tip SHA (ACP) | `a8c5373` |
| Epic | V5 governance & transparency |
| `stopped_reason` | `group_boundary_stop` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-006.md
tickets_done: 3 / 6
next_ticket_id: T03
blocker: none
stopped_reason: group_boundary_stop
tip_sha: a8c5373
```

## Slice outcome

- Goal completed (one sentence): ADR vs graph drift report lists missing/extra edges; fail-soft on CT103.
- Slice doc path: `docs/slice-v5-t04-architecture-drift.md`
- Deploy verify path / status: `pass` (T04 smoke; combined dual-lane floor owned by T03)
- CT103 tip / CT104 tip: `a8c5373` / `a8c5373`

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: _(none)_
- Actions run IDs: 717, 718, 719
- Session / run IDs: unit `tests/test_adr_drift_t04.py`; live `T04_DRIFT_REPORT_OK` + `T04_FAIL_SOFT_OK`
- ADR IDs: ADR-0022

## Decisions the next coordinator must honor

1. Dual-lane: T03 owns combined DEPLOY_VERIFY floor for this wave; T04 smoke already PASS on `a8c5373`.
2. Drift CLI is fail-soft by default (`agentctl graph drift`); `--strict` is opt-in only.
3. Do not start T05 until T03 or T04 Done (T04 Done); T06 still needs T02+T03.

## Next coordinator: first actions

1. If T03 still open: finish review replay + combined tip verify (rebase onto latest main if needed).
2. Else advance to T05 SARIF ingest.
3. Prefer rebase onto tip that includes both T03+T04 before marking dual-lane wave complete.

## Open risks (one line each)

- Catalog `adr_constrains_service` edges are not in the ADR-fact compare set; may show as extras if later included.
