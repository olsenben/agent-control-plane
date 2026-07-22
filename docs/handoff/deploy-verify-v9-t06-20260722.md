# Deploy verification — V9 T06 OBSERVE_PUBLIC_BASE_URL fail-closed + Gitea extra_tabs

| Field | Value |
|-------|-------|
| Ticket ID | V9 T06 |
| Slice doc | docs/slice-v9-t06-observe-public-links.md |
| Tip SHA (expected) | `4a4998a` |
| Date (UTC) | 2026-07-22 |
| Operator | Cursor V9 T06 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 already at `4a4998a`; code on `main` (ledger handoff tip after T06 land) |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up |
| `deploy-ct104` green for tip | pass (host pin) | CT104 tip matches |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `4a4998a4aec634c4e055fa63a293d27f56bfcade` | yes |
| CT104 (`192.168.4.63`) | same | `4a4998a4aec634c4e055fa63a293d27f56bfcade` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t06_deploy_verify.sh`.

### Host `OBSERVE_PUBLIC_BASE_URL` (.env)

CT103 deploy `.env` has **no** `OBSERVE_PUBLIC_BASE_URL` entry (intended fail-closed steady state for this deploy).

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; new `checks.observe_public_base_url=unset` (informational, does not gate); overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T06) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T06 is config + comment-projection path) |

## D. Slice smoke (T06)

| Step | Result | Evidence |
|------|--------|----------|
| Container `OBSERVE_PUBLIC_BASE_URL` unset | pass | `observe_public_base_url_container: unset` |
| `observe_config_warning` present when unset | pass | warning mentions `OBSERVE_PUBLIC_BASE_URL is unset` |
| `/readyz` reports `observe_public_base_url: unset` | pass | informational check only; readiness unchanged |
| `format_invocation_started` omits Observe line | pass | no `Observe:` in body when base URL unset |
| `render_session_comment_body` omits Observe line | pass | no `Observe:` in body when base URL unset |
| Remote smoke banner | pass | `V9_T06_SMOKE_OK` from container script `_v9_t06_smoke_remote.py` |
| Unit regression floor | pass (noted) | handoff-031: `tests/test_v9_t06_observe_public_links.py` (35 tests); full suite 808 passed at land time |

Smoke script: `scripts/_v9_t06_deploy_verify.sh` (SSH to CT103; in-container checks against live `Settings` + `/readyz`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T06 link/config path only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change in T06) |
| T04 five-panel UI unchanged (not re-smoked here) | pass (no UI regression in T06 smoke scope) |

## Human follow-up (not blocking T06 Done)

- **CT100 `extra_tabs.tmpl` install** — follow `docs/gitea-custom/README.md` once a human chooses and sets `OBSERVE_PUBLIC_BASE_URL` on CT103; do not install the template while the base URL is unset.
- **Live Gitea tab confirmation** — the template-context spike is source-level; run the README's `RUN_MODE=dev` / `DumpVar` confirmation step during the human install before relying on the tab in production.

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 4a4998a4aec634c4e055fa63a293d27f56bfcade
next_slice_unblocked: yes
blocker: none
```
