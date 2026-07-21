# QA ledger — V6 post-epic sign-off

Driven from the approved QA plan (`.cursor/plans/v6_post-epic_qa_plan_7e624bba.plan.md`).
Epic tip baseline: `a9917b8` (docs tip `61a0e7e`).

| Field | Value |
|-------|-------|
| **Started** | 2026-07-21 |
| **Operator** | Cursor agent |
| **Tip under test** | `eda495d` (+ wave3 patches) |
| **Unit suite** | Wave3 focused: 16 passed; wave2+approval green |
| **Ruff** | pass |
| **Status** | Wave 3 complete — DUR/N0x/PATCH reconcile/observe auth matrix closed at unit level |

## Ticket status

| QA ID | Scope | Verdict | Notes |
|-------|-------|---------|-------|
| QA-T01 | Trace / provenance / projection | PASS | Durable `ledger_sequence` sort (F-12) |
| QA-T02 | Comment projection + status FSM | PASS (wave3) | FSM + PATCH + ambiguous GET reconcile |
| QA-T03 | Observatory auth | PASS (wave3) | Repo-read + 401/403 unit tests |
| QA-T04 | LiteLLM / budget / egress | PASS | Durable CT103 budget + `budget_exhausted` (F-07) |
| QA-T05 | Authorization + approval binding | PASS (wave3) | N01–N06/N08 mocked; base-SHA check |
| QA-T06 | Injection shadow | PASS | |
| QA-T07 | NL invocation FSM | PASS | Wired into state reduction + handoff (F-06) |
| QA-T08 | Eval export | PASS | |
| QA-REG | V4/V5 regression floor | PASS | |
| QA-DUR | Upgrade / restart durability | PASS (unit) | DUR-01–03/05/08/09 unit; homelab still optional |

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
| F-08 | High | **Fixed** (wave2+3) `_patch` + 404 successor + ambiguous GET reconcile |
| F-09 | High | **Fixed** (wave2+3) DUR unit matrix; homelab DUR deferred |
| F-10 | Medium | **Fixed** (wave2) `register_pending_ci` → WaitingForCI projection |
| F-11 | Medium | **Fixed** (wave2+3) `policy_source_sha` + N0x evaluate suite |
| F-12 | Medium | **Fixed** (wave2) Durable ledger_sequence sort |

## Patch bundles

| Wave | Artifact |
|------|----------|
| 1 | [qa-bundles/qa-v6-signoff-harden.patch](qa-bundles/qa-v6-signoff-harden.patch) |
| 2 | [qa-bundles/qa-v6-wave2.patch](qa-bundles/qa-v6-wave2.patch) / [qa-v6-wave2.md](qa-bundles/qa-v6-wave2.md) |
| 3 | [qa-bundles/qa-v6-wave3.patch](qa-bundles/qa-v6-wave3.patch) / [qa-v6-wave3.md](qa-bundles/qa-v6-wave3.md) |

## Evidence (wave 3)

```text
ruff check .                                                          → pass
pytest tests/test_qa_v6_wave3.py                                      → 16 passed
```

## Residual (non-blocking)

- Full homelab DUR soak / restart
- N07 approver-revoked-before-publish (live OAuth)
- Mid-SSE token revoke integration
- Real Gitea OAuth for Observatory (shared token remains gate)
