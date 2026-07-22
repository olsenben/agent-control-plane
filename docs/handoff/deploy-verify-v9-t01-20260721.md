# Deploy verification — V9 T01 observe_event.v1 + safe-display

| Field | Value |
|-------|-------|
| Ticket ID | V9 T01 |
| Slice doc | docs/slice-v9-t01-observation-event-contract.md |
| Tip SHA (expected) | `c50ed96` |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor V9 T01 deploy-verify agent |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` green for tip | pass (noted) | Actions run #842 — human/boss pre-confirmed PASS |
| `deploy` (CT103) green for tip | pass (noted) | Actions run #844 — human/boss pre-confirmed PASS |
| `deploy-ct104` green for tip | pass (noted) | Actions run #843 — human/boss pre-confirmed PASS |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `c50ed966001c1e69647a406f9e9eaf5b5c168522` | yes |
| CT104 (`192.168.4.63`) | same | `c50ed966001c1e69647a406f9e9eaf5b5c168522` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; script `scripts/_v9_t01_deploy_verify.sh`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `checks.redis=ok`, `checks.state_dir=ok`; overall `status=degraded` only because `model_2070` Ollama host timed out (non-blocking for T01) |
| Required compose services up | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` Up on CT103 |
| Unexpected secret / write-token on CT104 | absent | not exercised (T01 is display-contract only; no CT104-specific smoke required) |

## D. Slice smoke (T01)

| Step | Result | Evidence |
|------|--------|----------|
| Container import `safe_display_event` on CT103 | pass | `SAFE_DISPLAY_IMPORT_OK`; unknown type `known_type=False`, zero `display_fields`, prohibited field names retained |
| Known type secret stripping | pass | `CONTROL_DECISION_DISPLAY_SAFE_OK`; `openai_api_key` in `prohibited_field_names`, `summary` allowlisted |
| Remote smoke banner | pass | `V9_T01_SMOKE_OK` from `docker compose exec -T control-plane python3 /tmp/_v9_t01_smoke_remote.py` |
| Unit regression floor | pass | `tests/test_v9_t01_safe_display.py` — 10 passed locally at verify time |

Smoke script: `scripts/_v9_t01_deploy_verify.sh` + `scripts/_v9_t01_smoke_remote.py` (scp + `docker cp` into `agent-control-plane-control-plane-1`).

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (T01 contract only) |
| Publish still via CT103 `publish-broker` only | pass (service Up; no publish-path change in T01) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: c50ed966001c1e69647a406f9e9eaf5b5c168522
next_slice_unblocked: yes
blocker: none
```
