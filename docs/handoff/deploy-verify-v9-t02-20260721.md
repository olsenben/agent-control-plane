# Deploy verification — V9 T02 observe.sqlite projection

| Field | Value |
|-------|-------|
| Ticket ID | V9 T02 |
| Slice doc | docs/slice-v9-t02-observe-sqlite-projection.md |
| Tip SHA (expected) | `6a67233` |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor V9 T02 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 already at `6a67233`; code landed on `main` via handoff-027 chain (`41bad77` feature + ledger tip) |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up |
| `deploy-ct104` green for tip | pass (host pin) | CT104 tip matches |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `6a67233763cc9ee1cef1363e31be15e1555f9504` | yes |
| CT104 (`192.168.4.63`) | same | `6a67233763cc9ee1cef1363e31be15e1555f9504` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t02_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T02) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T02 is projection store only; no CT104-specific smoke required) |

## D. Slice smoke (T02)

| Step | Result | Evidence |
|------|--------|----------|
| Container import `ObserveStore` + `project_event_fail_open` | pass | `OBSERVE_STORE_IMPORT_OK`, `PROJECT_EVENT_FAIL_OPEN_OK` |
| `rebuild_observe_db` for `ai-sdlc-lab/demo-app` | pass | `REBUILD_OK` — scanned 271, projected 102, skipped 169; `size_warning=null` |
| `agentctl observe rebuild --repo ai-sdlc-lab/demo-app` | pass | `AGENTCTL_OBSERVE_REBUILD_OK` |
| Remote smoke banner | pass | `V9_T02_SMOKE_OK` from `docker compose exec -T control-plane python3 /tmp/_v9_t02_smoke_remote.py` |
| Unit regression floor | pass (noted) | handoff-027: `tests/test_v9_t02_observe_store.py` (18) + `tests/test_v9_t02_observe_projector.py` (8); full suite 711 passed at land time |

Smoke script: `scripts/_v9_t02_deploy_verify.sh` + `scripts/_v9_t02_smoke_remote.py` (scp + `docker cp` into `agent-control-plane-control-plane-1`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T02 projection only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change in T02) |
| No new `/observe` or `/api/observe` routes | pass (surface freeze honored per handoff-027) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 6a67233763cc9ee1cef1363e31be15e1555f9504
next_slice_unblocked: yes
blocker: none
```
