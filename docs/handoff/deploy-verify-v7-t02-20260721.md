# Deploy verification — V7 post-T02 pin

| Field | Value |
|-------|-------|
| Ticket ID | V7 T02 (post-signoff re-verify) |
| Tip SHA | `c3b3fb4` (feature `234e248`) |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor agent |

## Host tip pin

| Host | Tip | Match |
|------|-----|-------|
| CT103 | `c3b3fb4` | yes |
| CT104 | `c3b3fb4` | yes |

## Checks

| Check | Result |
|-------|--------|
| `/readyz` redis+state | ok (degraded overall — external model checks ok) |
| Observatory unauth | 401 |
| CT104 write token | absent |
| bakeoff_profiles.yaml | present |
| In-container T01+T02 smoke | `V7_DEPLOY_VERIFY_OK profiles 4` |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: c3b3fb4
next_slice_unblocked: yes
blocker: none
epic_progress: 2 / 5 (40%)
```

Gap fixed before continue: hosts were on feature tip `234e248` while origin docs tip was `c3b3fb4` — both hosts pinned to `c3b3fb4`.
