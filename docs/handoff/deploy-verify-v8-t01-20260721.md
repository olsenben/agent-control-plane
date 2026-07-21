# Deploy verification — V8 T01 Homelab DUR soak / restart

| Field | Value |
|-------|-------|
| Ticket ID | V8 T01 |
| Slice doc | docs/slice-v8-t01-dur-soak.md |
| Tip SHA (expected) | docs/script commit on `main` (soak executed against live baseline `c274c07`) |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor V8 T01 agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` | N/A | Docs + soak script only; no product code |
| `deploy` (CT103) | N/A | Soak uses SSH restart of already-deployed tip `c274c07`; script runs from operator WSL |
| `deploy-ct104` | N/A | Optional light worker restart only; no image rebuild |

## B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `c274c07c4048a06071d41a5e63c53aa162dd394b` | yes (V8 baseline) |
| CT104 (`192.168.4.63`) | `3651bfe` (observed) | N/A for this ops soak — worker restart only; state proof is CT103 NFS |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` before | ok (degraded) | redis=ok state_dir=ok; model_2070 unreachable |
| CT103 `/readyz` after bounce | ok (degraded) | redis=ok state_dir=ok |
| Compose services | ok | control-plane + worker-state restarted; redis left up |
| CT104 write tokens | absent | `worker-report` env grep clean |

## D. Slice smoke (T01)

| Step | Result | Evidence |
|------|--------|----------|
| `scripts/_v8_t01_dur_soak.sh` | pass | `V8_T01_DUR_SOAK_PASS` @ 2026-07-21T23:16:35Z |
| Seed + before FP | pass | soak_tag `20260721T231610Z-48cad1fd`; seqs 1,2; budget attempts=1 |
| Restart CT103 control-plane | pass | compose restart control-plane + worker-state |
| After FP continuity | pass | same id→seq; projection unchanged; counter continued 2→3 |
| NFS cross-check | pass | `/mnt/agent-state/.../ledger_seq.txt` = 3; budget JSON present |
| Optional CT104 worker-report restart | pass | `V8_T01_CT104_WORKER_RESTART_OK`; `POST_CT104_STATE_OK` |

## E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass (ops soak only) |
| Risk 2 still requires approval + sandbox | N/A (not exercised) |
| Publish still via CT103 `publish-broker` only | N/A (not exercised); broker left running |
| No CT104 Gitea write tokens | pass |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: c274c07 (live soak baseline); docs tip = this commit
next_slice_unblocked: yes
blocker: none
```
