# Deploy verification — V9 T03 Protected SSE + Redis id-notify

| Field | Value |
|-------|-------|
| Ticket ID | V9 T03 |
| Slice doc | docs/slice-v9-t03-protected-sse-redis-notify.md |
| Tip SHA (expected) | `dae78e3` |
| Date (UTC) | 2026-07-22 |
| Operator | Cursor V9 T03 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 already at `dae78e3`; feature commit `23f8457` + ledger handoff `dae78e3` on `main` |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up |
| `deploy-ct104` green for tip | pass (host pin) | CT104 tip matches |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `dae78e3bd5962606c13b8f5d8cecec77c75d3e73` | yes |
| CT104 (`192.168.4.63`) | same | `dae78e3bd5962606c13b8f5d8cecec77c75d3e73` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t03_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T03) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T03 is CT103 SSE + Redis notify) |

## D. Slice smoke (T03)

| Step | Result | Evidence |
|------|--------|----------|
| Unauth SSE → 401 (never 200 + streamed error) | pass | `GET /api/observe/v1/sessions/run-v9t03-smoke/stream` without auth → `401` |
| Auth SSE headers (`X-Accel-Buffering: no`, `Cache-Control: no-cache`) | pass | auth stream → `200`; `x-accel-buffering: no`, `cache-control: no-cache` |
| History replay via `?after_sequence=0` | pass | SSE frames `id: 1`, `id: 2` from `observe.sqlite` |
| Live notify after ledger append (Redis ids-only) | pass | mid-stream append projected sequence `3`; `LIVE_NOTIFY_OK` |
| Shared token path | pass | pre-existing `.observe_shared_token` on CT103 (`SHARED_TOKEN_AVAILABLE=yes`) |
| Remote smoke banner | pass | `V9_T03_SMOKE_OK` from container script `_v9_t03_smoke_remote.py` |
| NPM `proxy_buffering off` live check | N/A | no NPM admin access from this operator; app-tier headers verified; documented human follow-up per slice doc |
| Unit regression floor | pass (noted) | handoff-029: `tests/test_v9_t03_protected_sse.py` (14 tests) + ported V8 T03 mid-SSE revoke; full suite 756 passed at land time |

Smoke script: `scripts/_v9_t03_deploy_verify.sh` (SSH to CT103; in-container urllib SSE against `127.0.0.1:8080`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T03 SSE path only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change in T03) |
| T05 auth matrix preserved (unauth SSE → 401, not redirect) | pass |

## Human follow-up (not blocking T03 Done)

NPM reverse-proxy `proxy_buffering off;` for the Observatory SSE path remains documented in the slice doc but not live-verified from this sandbox. Confirm when a browser `EventSource` is exercised through NPM (T04 UI).

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: dae78e3bd5962606c13b8f5d8cecec77c75d3e73
next_slice_unblocked: yes
blocker: none
```
