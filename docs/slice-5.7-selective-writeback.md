# Slice 5.7 — Selective Writeback from Session Trace

**Status:** Implemented + deploy verified 2026-07-20 (`a7dd4c5`)  
**Date:** 2026-07-20  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) PR-S5  
**Epic ticket:** T02  
**Builds on:** [slice-5.6-verification-evidence-gate.md](slice-5.6-verification-evidence-gate.md)  
**ADR:** [0013-session-trace-selective-writeback.md](adr/0013-session-trace-selective-writeback.md)

## Goal

On successful `session_finished` for review/plan, CT103 admits `memory_record.v1` from the session trace (structured result + preflight/verification evidence refs). Distinct from 6E.2 CI-verified fix memory.

## Deploy verification (2026-07-20)

| Check | Result |
|-------|--------|
| Tip | `a7dd4c5` (`feat(memory): Slice 5.7 selective writeback from session trace`) |
| Actions | 3 runs for tip — all `success` |
| CT103 / CT104 host tip | both `a7dd4c5` |
| CT103 `/readyz` | redis/state ok (overall may show degraded if optional model path soft-fails) |
| In-container smoke | `import_ok` + `test_session_writeback_57.py` **3 passed** |

```text
DEPLOY_VERIFY: PASS
tip: a7dd4c5
next_slice_unblocked: yes
blocker: none
```

## Locked policy

| Path | Behavior |
|------|----------|
| Typed review/plan success | After `verification_missing` + `session_finished` → admit memory (`structured_result`, `epistemic_status=inferred`) |
| Typed review/plan failure | No admission |
| Fix / repair | **No** 5.7 admission — 6E.2 owns `ci_verified` writeback |
| Legacy ingest (no typed session) | Keep early `writeback_from_completed` (model_generated) |

## Admission rules

Admit only when all hold:

1. Session status is `finished`
2. `command_kind` in `{review, plan}`
3. `run_id` listed on the session
4. Durable `verification_claim` present and identity matches
5. Mapper produces a structured `memory_record.v1`

Fields stamped on admit:

- `session_id`
- `epistemic_status` from claim (`inferred` for missing; `verified`/`invalidated` reserved for passed/failed)
- `evidence_refs` (session, run, preflight digest, verification digest/status, summary hash)
- `verification_scope` (claim scope SHA)
- `admission_policy_version` = `session_trace_5.7.0`
- `memory_quality` = `structured_result`

## Events

- `agent.memory_admitted`
- `agent.memory_rejected` (reason in payload)

## vs 6E.2

| | 5.7 session trace | 6E.2 CI memory |
|--|-------------------|----------------|
| Trigger | `session_finished` (review/plan) | CI verdict=`verified` (fix) |
| Quality | `structured_result` | `ci_verified` |
| Epistemic | usually `inferred` | verified outcome |

## Tests

`tests/test_session_writeback_57.py` — admit with evidence, typed ingest path, failed skip.

## Deploy verification

See [Deploy verification (2026-07-20)](#deploy-verification-2026-07-20) above.

## Follow-on

- **T03** — V4.1.2 exit (homelab review+plan+fake fix + second plan retrieves admitted memory)
- Adequacy profile (T04)
