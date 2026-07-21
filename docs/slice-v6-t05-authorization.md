# Slice V6 T05 — Authorization decisions and attribution

**Status:** Done — deploy verify PASS tip `1dff508` (2026-07-21)  
**Date:** 2026-07-21  
**Epic ticket:** T05  
**Deps:** T01 Done  

## Goal

Record separate authorization predicates (`authorization_decision.v1`), keep invoker/approver/acting identity distinct, recheck mutation-critical authority before publish, and stamp commit trailers for attribution. Accept ADR-0017.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Predicates | invoker / approver / bot write / policy / approval_scope evaluated separately | pass |
| Read-only plan | Invoker with repo read may `/agent plan` without write | pass |
| Approve | Non-approver denied; owner/configured approver allowed | pass |
| Fix enqueue | `invoked_by` = fix requester; `approved_by` = approval grantor | pass |
| Pre-publish | Recheck fails on source SHA drift or lost bot write | pass |
| Trailers | `Invoked-By`, `Agent-Run`, `Agent-Session` (+ optional `Approved-By`) | pass |
| ADR-0017 | status `accepted` | pass |

## Artifacts

| Path | Role |
|------|------|
| `src/agent_shared/models/authorization_decision.py` | Schema + evaluate |
| `src/agent_control/authorization.py` | Command helpers + ledger event |
| `src/agent_control/publish/broker.py` | Pre-publish recheck + trailers |
| `src/agent_workers/publish/formatters.py` | Commit trailers |
| `docs/adr/0017-acting-vs-invoker-identity.md` | Accepted |
| `tests/test_v6_t05_authorization.py` | Unit coverage |

## Deploy verification

| Field | Value |
|-------|-------|
| Tip SHA | `1dff508` |
| Verdict | **DEPLOY_VERIFY: PASS** |
| Smoke | `V6_T05_SMOKE_OK` |
| CT103/CT104 | tip pin match; Actions success |
