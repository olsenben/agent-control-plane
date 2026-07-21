# Deploy verification — QA V6 post-epic tip

| Field | Value |
|-------|-------|
| Ticket ID | QA-SIGNOFF (waves 1–3) |
| Slice doc | [qa-v6-ledger.md](qa-v6-ledger.md) |
| Tip SHA (expected) | `28292c0` |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | N/A | Manual tip deploy; unit suite green locally (wave3 16 passed) |
| `deploy` (CT103) | N/A | Manual `_deploy_tip` + verify script |
| `deploy-ct104` | N/A | Manual CT104 rebuild in verify script |

## B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `28292c0` | yes |
| CT104 (`192.168.4.63`) | `28292c0` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` | ok (degraded) | redis+state ok; external model checks ok |
| Required compose services up | ok | control-plane, publish-broker, worker-state, redis |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

## D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Observatory unauthenticated → 401 | pass | `OBSERVE_AUTH_GATE_OK` on `/observe/repos/...` |
| Eval export + CAS verify | pass | `QA_V6_SMOKE_OK 421ba4e0c05d` |
| Wave3 symbols present | pass | `get_issue_comment`, `_reconcile_patch_applied` |

## E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | pass |
| Risk 2 approval+sandbox unchanged | N/A (not exercised) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 28292c0
next_slice_unblocked: yes
blocker: none
```
