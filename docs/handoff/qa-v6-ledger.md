# QA ledger — V6 post-epic sign-off

Driven from the approved QA plan (`.cursor/plans/v6_post-epic_qa_plan_7e624bba.plan.md`).
Epic tip baseline: `a9917b8` (docs tip `61a0e7e`).

| Field | Value |
|-------|-------|
| **Started** | 2026-07-21 |
| **Operator** | Cursor agent |
| **Tip under test** | `28292c0` |
| **Unit suite** | Wave3: 16 passed; waves 1–2 green |
| **Ruff** | pass |
| **Status** | **SIGNED OFF** — deploy verify PASS on CT103/CT104 |
| **Sign-off date (UTC)** | 2026-07-21 |
| **Deploy evidence** | [deploy-verify-qa-v6-20260721.md](deploy-verify-qa-v6-20260721.md) |

## Ticket status

| QA ID | Scope | Verdict | Notes |
|-------|-------|---------|-------|
| QA-T01 | Trace / provenance / projection | PASS | Durable `ledger_sequence` sort (F-12) |
| QA-T02 | Comment projection + status FSM | PASS | FSM + PATCH + ambiguous GET reconcile |
| QA-T03 | Observatory auth | PASS | Repo-read + live 401 gate |
| QA-T04 | LiteLLM / budget / egress | PASS | Durable CT103 budget + `budget_exhausted` (F-07) |
| QA-T05 | Authorization + approval binding | PASS | N01–N06/N08 mocked; base-SHA check |
| QA-T06 | Injection shadow | PASS | |
| QA-T07 | NL invocation FSM | PASS | Wired into state reduction + handoff (F-06) |
| QA-T08 | Eval export | PASS | Live `QA_V6_SMOKE_OK` |
| QA-REG | V4/V5 regression floor | PASS | |
| QA-DUR | Upgrade / restart durability | PASS (unit) | Homelab soak deferred (residual) |

## Failures

| ID | Severity | Disposition |
|----|----------|-------------|
| F-01–F-12 | — | **Fixed** across waves 1–3 (see prior sections / patch bundles) |

## Patch bundles

| Wave | Artifact |
|------|----------|
| 1 | [qa-bundles/qa-v6-signoff-harden.patch](qa-bundles/qa-v6-signoff-harden.patch) |
| 2 | [qa-bundles/qa-v6-wave2.patch](qa-bundles/qa-v6-wave2.patch) / [qa-v6-wave2.md](qa-bundles/qa-v6-wave2.md) |
| 3 | [qa-bundles/qa-v6-wave3.patch](qa-bundles/qa-v6-wave3.patch) / [qa-v6-wave3.md](qa-bundles/qa-v6-wave3.md) |

## Evidence (deploy sign-off)

```text
DEPLOY_VERIFY: PASS tip=28292c0
CT103 + CT104 tip pin match
OBSERVE_AUTH_GATE_OK (401)
QA_V6_SMOKE_OK
```

## Deferred residual (explicitly saved for later)

- Full homelab DUR soak / restart
- N07 approver-revoked-before-publish (live OAuth)
- Mid-SSE token revoke integration
- Real Gitea OAuth for Observatory (shared token remains gate)
