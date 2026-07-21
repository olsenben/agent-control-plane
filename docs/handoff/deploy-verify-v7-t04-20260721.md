# Deploy verification — V7 T04 memory isolation

| Field | Value |
|-------|-------|
| Ticket ID | V7 T04 |
| Slice doc | docs/slice-v7-t04-memory-isolation.md |
| Tip SHA (expected) | `47724d1` (feature `47cde2b`; docs tip origin/main) |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test / ci / deploy / deploy-ct104 | pass (known) | Actions GREEN for tip `47724d1` |

## B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `47724d1c239b021af92e083fcae1908b8cf3d651` | yes |
| CT104 (`192.168.4.63`) | `47724d1c239b021af92e083fcae1908b8cf3d651` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` | ok (degraded) | redis+state ok; model_2070 unreachable |
| Compose services | ok | control-plane running |

## D. Slice smoke (T04)

| Step | Result | Evidence |
|------|--------|----------|
| `scripts/_v7_t04_smoke.sh 47724d1` | pass | `V7_T04_SMOKE_OK namespaces 4`; prod refuse; 4 isolated namespaces; `production_memory_touched=false` |

## E. Regression floor

| Check | Result |
|-------|--------|
| No protected main mutation by agent path | pass (N/A for this smoke) |
| Bake-off namespaces only under `bakeoff/*` | pass |
| Prod MemoryStore not opened | pass |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 47724d1
next_slice_unblocked: yes
blocker: none
```
