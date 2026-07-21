# QA ledger — V6 post-epic sign-off

Driven from the approved QA plan (`.cursor/plans/v6_post-epic_qa_plan_7e624bba.plan.md`).
Epic tip baseline: `a9917b8` (docs tip `61a0e7e`).

| Field | Value |
|-------|-------|
| **Started** | 2026-07-21 |
| **Operator** | Cursor agent |
| **Tip under test** | `61a0e7e` (+ wave1 + wave2 patches) |
| **Unit suite** | Wave2 focused: 70 passed; V6 modules green |
| **Ruff** | pass |
| **Status** | Wave 2 complete — residual F-06–F-12 addressed; thin gaps remain |

## Ticket status

| QA ID | Scope | Verdict | Notes |
|-------|-------|---------|-------|
| QA-T01 | Trace / provenance / projection | PASS (wave2) | Durable `ledger_sequence` sort (F-12) |
| QA-T02 | Comment projection + status FSM | PASS (wave2) | FSM + PATCH matrix + `_patch` + successor (F-08) |
| QA-T03 | Observatory auth | PASS (wave1) | Repo-read on all surfaces |
| QA-T04 | LiteLLM / budget / egress | PASS (wave2) | Durable CT103 budget + `budget_exhausted` (F-07) |
| QA-T05 | Authorization + approval binding | PASS (wave2) | `policy_source_sha` bind + fail-closed (F-11) |
| QA-T06 | Injection shadow | PASS (wave1) | |
| QA-T07 | NL invocation FSM | PASS (wave2) | Wired into state reduction + handoff (F-06) |
| QA-T08 | Eval export | PASS (wave1) | |
| QA-REG | V4/V5 regression floor | PASS | |
| QA-DUR | Upgrade / restart durability | PARTIAL | Projection rebuild DUR-09; full DUR-01–08 still thin |

## Failures

| ID | Severity | Disposition |
|----|----------|-------------|
| F-01 | Critical | **Fixed** (wave1) Observatory auth |
| F-02 | High | **Fixed** (wave1) Shadow semantics |
| F-03 | High | **Fixed** (wave1) Status FSM |
| F-04 | High | **Fixed** (wave1+2) Fail-closed permission (authorization + gitea_client) |
| F-05 | High | **Fixed** (wave1) Eval missing artifact |
| F-06 | Critical | **Fixed** (wave2) NL wire + clarification + handoff stub |
| F-07 | High | **Fixed** (wave2) Durable budget + `budget_exhausted` control_decision |
| F-08 | High | **Fixed** (wave2) `_patch` + 404 successor + retryable no-advance |
| F-09 | High | **Partial** (wave2) DUR-09 rebuild test; broader upgrade suite deferred |
| F-10 | Medium | **Fixed** (wave2) `register_pending_ci` → WaitingForCI projection |
| F-11 | Medium | **Fixed** (wave2) `policy_source_sha` on approval + evaluate check |
| F-12 | Medium | **Fixed** (wave2) Durable ledger_sequence sort |

## Patch bundles

| Wave | Artifact |
|------|----------|
| 1 | [qa-bundles/qa-v6-signoff-harden.patch](qa-bundles/qa-v6-signoff-harden.patch) |
| 2 | [qa-bundles/qa-v6-wave2.patch](qa-bundles/qa-v6-wave2.patch) / [qa-v6-wave2.md](qa-bundles/qa-v6-wave2.md) |

## Evidence (wave 2)

```text
ruff check .                                                          → pass
pytest tests/test_qa_v6_wave2.py + V6 + approval + ci_truth          → 70 passed
```
