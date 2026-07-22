# QA ledger — V8 residual (from V6 deferred)

Tracks the four items deferred at QA V6 SIGNED OFF. Epic: [boss-ledger-v8.md](boss-ledger-v8.md). Parent: [qa-v6-ledger.md](qa-v6-ledger.md).

| Field | Value |
|-------|-------|
| **Started** | — (epic ready, not started) |
| **Baseline tip** | `c274c07` (post-V7) |
| **Status** | READY |
| **Parent QA** | V6 SIGNED OFF tip `28292c0` |

## Tickets

| QA / epic ID | Scope | Verdict | Notes |
|--------------|-------|---------|-------|
| QA-V8-T01 / T01 | Homelab DUR soak / restart | Todo | Unit DUR already PASS; need live bounce |
| QA-V8-T02 / T02 | N07 approver-revoked-before-publish (live) | Todo | Mocked N01–N06/N08 done in V6 wave3 |
| QA-V8-T03 / T03 | Mid-SSE token revoke integration | Todo | Code claims mid-stream re-check; live proof open |
| QA-V8-T04 / T04 | Real Observatory Gitea OAuth | Todo | Shared token remains interim gate |

## Deferred → owned

| V6 residual line | V8 ticket |
|------------------|-----------|
| Full homelab DUR soak / restart | T01 |
| N07 approver-revoked-before-publish (live OAuth) | T02 |
| Mid-SSE token revoke integration | T03 |
| Real Gitea OAuth for Observatory | T04 |
