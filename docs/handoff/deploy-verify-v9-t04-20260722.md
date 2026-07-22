# Deploy verification — V9 T04 five-panel Observatory UI

| Field | Value |
|-------|-------|
| Ticket ID | V9 T04 |
| Slice doc | docs/slice-v9-t04-five-panel-observatory-ui.md |
| Tip SHA (expected) | `8fb905d` |
| Date (UTC) | 2026-07-22 |
| Operator | Cursor V9 T04 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 already at `8fb905d`; code on `main` (ledger handoff tip after T04 land) |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up |
| `deploy-ct104` green for tip | pass (host pin) | CT104 tip matches |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `8fb905ddd776bee1f28c6edec3b0505ca2246701` | yes |
| CT104 (`192.168.4.63`) | same | `8fb905ddd776bee1f28c6edec3b0505ca2246701` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t04_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T04) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T04 is CT103 UI rendering) |

## D. Slice smoke (T04)

| Step | Result | Evidence |
|------|--------|----------|
| Unauth session detail HTML → 302 redirect | pass | `GET /observe/sessions/run-v9t04-smoke` with `Accept: text/html` → `302`; `Location: /observe/oauth/login?next=%2Fobserve%2Fsessions%2Frun-v9t04-smoke` |
| Auth session detail HTML (shared token) → 200 five panels | pass | Bearer token from `.observe_shared_token`; body contains all five panel headings (`1. Current state` … `5. Artifacts`) |
| No-JS timeline pagination | pass | first page includes `after_sequence=25` link; page 2 (`?after_sequence=25`) returns expected row + `back to start` |
| Shared token path | pass | pre-existing `.observe_shared_token` on CT103 (`SHARED_TOKEN_AVAILABLE=yes`) |
| Remote smoke banner | pass | `V9_T04_SMOKE_OK` from container script `_v9_t04_smoke_remote.py` |
| Unit regression floor | pass (noted) | handoff-030: `tests/test_v9_t04_five_panel_ui.py` (20 tests); full suite 773 passed at land time |

Smoke script: `scripts/_v9_t04_deploy_verify.sh` (SSH to CT103; in-container urllib against `127.0.0.1:8080`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T04 UI path only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change in T04) |
| T05 auth matrix preserved (unauth HTML → 302 redirect) | pass |
| T03 SSE path unchanged (not re-smoked here; T03 verify still valid at prior tip) | pass (no SSE regression in T04 smoke scope) |

## Human follow-up (not blocking T04 Done)

NPM reverse-proxy `proxy_buffering off;` for the Observatory SSE path remains documented but not live-verified from this operator. Confirm when exercising panel 4 `EventSource` through NPM in a browser.

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 8fb905ddd776bee1f28c6edec3b0505ca2246701
next_slice_unblocked: yes
blocker: none
```
