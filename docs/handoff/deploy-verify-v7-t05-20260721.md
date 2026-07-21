# Deploy verification — V7 T05 bake-off report

| Field | Value |
|-------|-------|
| Ticket ID | V7 T05 |
| Slice doc | docs/slice-v7-t05-bakeoff-report.md |
| Tip SHA (expected) | `573a777` (feature `fc446b6`; docs tip origin/main) |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test / ci / deploy / deploy-ct104 | pass (known) | Actions GREEN for tip `573a777` |

## B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `573a777403be56baf5183d59513c8f8b6163c173` | yes |
| CT104 (`192.168.4.63`) | `573a777403be56baf5183d59513c8f8b6163c173` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` | ok (degraded) | redis+state ok; model_2070 unreachable |
| Compose services | ok | control-plane running |

## D. Slice smoke (T05)

| Step | Result | Evidence |
|------|--------|----------|
| `scripts/_v7_t05_smoke.sh 573a777` | pass | `V7_T05_SMOKE_OK profiles 4 gates_ok True`; bakeoff_report.v1; unbounded_recursion=false; injection_shadow_is_authority=false; production_memory_touched=false |

## E. Regression floor

| Check | Result |
|-------|--------|
| Unbounded recursion still off | pass |
| Shadow injection ≠ authority | pass |
| No production memory mutation | pass |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 573a777
next_slice_unblocked: yes
blocker: none
epic_status: complete
```
