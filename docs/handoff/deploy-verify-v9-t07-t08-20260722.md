# Deploy verification — V9 T07+T08 decisions/artifacts + CT102 CI channel

| Field | Value |
|-------|-------|
| Ticket ID | V9 T07 ∥ T08 |
| Slice docs | docs/slice-v9-t07-decisions-artifacts.md, docs/slice-v9-t08-ci-observatory-channel.md |
| Tip SHA (verified) | `fba0846` |
| Wave tip (requested) | `5b3f9da` (ledger handoff after `df1d6d8` functional land; `fba0846` is the functional superset verified here) |
| Date (UTC) | 2026-07-22 |
| Operator | Cursor V9 T07+T08 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (host pin) | CT103+CT104 pinned to `fba0846`; code on `main` |
| `deploy` (CT103) green for tip | pass (host pin) | CT103 tip matches; compose services Up; control-plane rebuilt after CT104 pin |
| `deploy-ct104` green for tip | pass (host pin) | CT104 was ahead at `4bbf438`; pinned to `fba0846` to match CT103 |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `fba0846624fc5dfbdf762b06391d181ef9ce7beb` | yes |
| CT104 (`192.168.4.63`) | same | `fba0846624fc5dfbdf762b06391d181ef9ce7beb` | yes (after pin) |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t07_t08_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running; prior waves report `checks.redis=ok`, `checks.state_dir=ok` |
| Required compose services up | ok | all four core services running on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T07/T08 are CT103 observe path) |

## D. Slice smoke (T07)

| Step | Result | Evidence |
|------|--------|----------|
| `decisions_panel_view` returns structured decision (shared-token auth path) | pass | `decisions_panel_view: ok`; why=`risk1 requires sign-off` |
| Panel 3 HTML renders decision fields via shared token | pass | `auth_detail_code: 200`; markers present |
| Panel 5 artifact rows default `metadata_only` | pass | `artifact_disposition_metadata_only: ok` |
| Redacted artifact view (no secret leakage) | pass | `artifact_view_code: 200`; `artifact_redacted_view: ok` |
| Path traversal on artifact view rejected | pass | `path_traversal_code: 404`; `path_traversal_rejected: ok` |
| Remote smoke banner | pass | `V9_T07_SMOKE_OK` |

## D2. Slice smoke (T08)

| Step | Result | Evidence |
|------|--------|----------|
| `agent.fix_ci_*` projected into `observe.sqlite` | pass | `observe_ci_rows: 1`; `projector_fix_ci_observed: ok` |
| CI category/event visible on session timeline | pass | `t08_detail_code: 200`; `timeline_ci_marker: ok` |
| Terminal session no-regress on late duplicate verdict | pass | session `FINISHED` after verified verdict; late `failing` rev=1 no-op; `terminal_no_regress: ok` |
| Remote smoke banner | pass | `V9_T08_SMOKE_OK`, `V9_T07_T08_SMOKE_OK` |

Smoke script: `scripts/_v9_t07_t08_deploy_verify.sh` (SSH to CT103; in-container `scripts/_v9_t07_t08_smoke_remote.py`).

Non-blocking noise: `session_comment_projection_failed` on Gitea issue comment POST (500 from CT100 demo-app issue 99008) during T08 seed — comment projection is fail-open and did not affect smoke verdict.

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T07/T08 observe path only) |
| Publish still via CT103 `publish-broker` only | pass (service running; no publish-path change) |
| T04 five-panel / T05 auth matrix preserved | pass (shared-token auth detail 200; path traversal 404) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: fba0846624fc5dfbdf762b06391d181ef9ce7beb
next_slice_unblocked: yes (V9 epic complete)
blocker: none
```
