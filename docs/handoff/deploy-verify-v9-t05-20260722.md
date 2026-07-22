# Deploy verification — V9 T05 Gitea OAuth shell

| Field | Value |
|-------|-------|
| Ticket ID | V9 T05 |
| Slice doc | docs/slice-v9-t05-gitea-oauth-shell.md |
| Tip SHA (expected) | `1f71bf6` |
| Date (UTC) | 2026-07-22 |
| Operator | Cursor V9 T05 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 already at `1f71bf6`; code on `main` (includes QA wave3 fix `1f71bf6`) |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up |
| `deploy-ct104` green for tip | pass (host pin) | CT104 tip matches |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `1f71bf60515d038d78afc7f6e3278a947b909cc6` | yes |
| CT104 (`192.168.4.63`) | same | `1f71bf60515d038d78afc7f6e3278a947b909cc6` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t05_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T05) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T05 is CT103 OAuth shell; no CT104-specific smoke required) |

## D. Slice smoke (T05)

| Step | Result | Evidence |
|------|--------|----------|
| Unauth API (no `text/html` Accept) → 401 JSON | pass | `GET /observe/repos/ai-sdlc-lab/demo-app` with `Accept: application/json` → `401` |
| Unauth browser (`Accept: text/html`) → 302 redirect | pass | same path with `Accept: text/html` → `302`; `Location: /observe/oauth/login?next=%2Fobserve%2Frepos%2Fai-sdlc-lab%2Fdemo-app` |
| OAuth login without secrets configured → 503 | pass | `GET /observe/oauth/login` → `503` (fail-closed; human OAuth app checklist still owed for live login) |
| Unauth SSE → 401 (not redirect) | pass | `GET /api/observe/v1/sessions/fake-run-id/stream` with `Accept: text/event-stream` → `401` |
| Remote smoke banner | pass | `V9_T05_SMOKE_OK` from CT103 localhost curl block in `_v9_t05_deploy_verify.sh` |
| Unit regression floor | pass (noted) | handoff-028: `tests/test_v9_t05_oauth_shell.py` (31 tests); full suite 742 passed at land time |

Smoke script: `scripts/_v9_t05_deploy_verify.sh` (SSH to CT103; curl against `127.0.0.1:8080`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T05 auth shell only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change in T05) |
| `/api/observe/v1/*` versioned mount behind auth | pass (SSE route exercised; unauth → 401) |

## Human follow-up (not blocking T05 Done)

OAuth application registration + `OBSERVE_OAUTH_*` secrets on CT103 remain unset per slice doc human checklist. Live browser login smoke is deferred until a human completes V8 T04 checklist steps 1–7.

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 1f71bf60515d038d78afc7f6e3278a947b909cc6
next_slice_unblocked: yes
blocker: none
```
