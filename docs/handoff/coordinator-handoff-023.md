# Handoff — coordinator-handoff-023

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 023 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | V8 T02 |
| Tip SHA (ACP) | 9f92594 |
| Epic | V8 residual QA |
| `stopped_reason` | `blocker` (WaitingHuman — disposable approver) |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-023.md
tickets_done: 0 / 4
next_ticket_id: T01|T03 (disjoint OK) / T02 WaitingHuman
blocker: need disposable Gitea user for N07 collaborator revoke
stopped_reason: blocker
```

## Slice outcome

- Goal completed: harness + hermetic N07 + publish write-recheck shipped; live proof blocked on disposable human principal.
- Slice doc: docs/slice-v8-t02-n07-live.md
- Deploy verify: pending human + tip deploy + `_v8_t02_n07_live.sh` PASS
- CT103 / CT104: N/A until live re-run after disposable user exists

## Evidence pointers

- Unit: `tests/test_qa_v6_wave3.py::test_n07_approver_revoked_before_publish`
- Probe/live: `scripts/_v8_t02_n07_probe.sh`, `scripts/_v8_t02_n07_live.sh`
- Evidence: `docs/handoff/evidence/v8-t02-n07-*.txt`
- ADR: none (extends ADR-0017 publish recheck; no new ADR)

## Decisions the next coordinator must honor

1. Do not revoke `olsenben` / production approver for N07.
2. Live Done requires `DISPOSABLE_APPROVER` existing user + CT103 tip with publish write-recheck.
3. T01/T03 may proceed in parallel while T02 is WaitingHuman.

## Next coordinator: first actions

1. After human creates disposable user: deploy tip, run `_v8_t02_n07_live.sh`, attach evidence, mark T02 Done.
2. Do not start T04 OAuth work from this handoff.

## Open risks (one line each)

- Until live PASS, N07 remains hermetic-only against a real Gitea permission change.
