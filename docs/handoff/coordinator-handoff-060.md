# Handoff — coordinator-handoff-060

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 060 |
| Date (UTC) | 2026-08-19 |
| Slice / ticket ID | VExp W1 Phase 4 DEV bakeoff |
| Tip SHA (ACP) | `2f15d82fa2122c7fbff443a0daf567442025d9e8` |
| maintenance-evals SHA | `8ff016beff6efac3e3108e73eb7d6c6661c2cf55` (local-only) |
| Epic | Verified Experience Control Plane (not V10) |
| `stopped_reason` | `blocker` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-060.md
tickets_done: W0 5/5; W1 coded + DEPLOY_VERIFY PASS; Phase 4 freeze recorded
next_ticket_id: W1 treatment-exposure repair
blocker: slot 14 e06 B1 missing context_pack hashes after parse-timeout
stopped_reason: blocker
decision: STOP_REPAIR
```

## Slice outcome

- Goal completed (one sentence): Official 14-slot unscored DEV bakeoff finished; freeze is STOP_REPAIR because one B1 slot did not expose a V2 pack.
- Result dir: `maintenance-evals/results/vexp-w1-context-v2-dev-v1`
- 13/14 treatment_ok; 0/14 verified_success
- Failed slot: `retry-toolkit-e06` `context_v2` `sess-eval-509576c0e89d4e59bba1d48e0fbd806c` (`evaluated_agent`: fix JSON parse + json-retry timeout; empty `context_pack_version`)

## Decisions the next coordinator must honor

1. Production default stays `CONTEXT_MODE=baseline_v1`. This freeze does not flip it.
2. Do not start WAVE 2 (repair) until W1 treatment exposure is complete.
3. Do not inspect reserved val/test splits.
4. Do not mutate frozen V10 manifests or `boss-ledger-v10.md`.
5. Re-run or repair e06 B1 so a V2 pack + hashes are on the session even when the solver fails to parse.

## Next coordinator: first actions

1. Persist treatment hashes on the failed-session path (parse timeout currently drops them).
2. Re-dispatch e06 B1 (or the full 14) only after that fix.
3. Re-freeze GO_VERIFIED / GO_EVIDENCE_ONLY / STOP_REPAIR from a complete-treatment result set.
