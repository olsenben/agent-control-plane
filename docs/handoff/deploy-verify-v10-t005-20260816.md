# Deploy verification — V10 T00.5 C0/C1 controller_backend truth

| Field | Value |
|-------|-------|
| Ticket ID | V10 T00.5 |
| Slice doc | `docs/slice-v10-t005-recursive-controller.md` |
| Tip SHA (requested) | `e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697` |
| Tip SHA (verified) | `e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697` on CT103 and CT104 |
| Date (UTC) | 2026-08-16 |
| Operator | t005-close deploy-verify agent |
| Status | `PASS` |

Run through WSL bash with the CT103/CT104 deploy key. Commands that inspect environment state must emit variable names or presence/absence only, never values.

## A. Host tip pin

- [x] CT103 and CT104 live repository tips match the requested T00.5 tip.
- [x] Deployed code includes `controller_backend` resolution and G2 telemetry from T00.5.

Evidence:

```text
CT103 tip: e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697
CT104 tip: e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697
```

Commands/checks:

```bash
git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD
```

Result: `PASS`

## B. Control-plane health

- [x] CT103 `/readyz` reports `ready`; Redis and state are `ok`.
- [x] Required compose services are up on CT103 and CT104.

Commands/checks:

```bash
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose ps
curl -fsS http://127.0.0.1:8080/readyz
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose -f docker-compose.ct104.yml ps
```

Result: `PASS`

## C. CT104 write-token and sandbox boundary

- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-rlm-root`.
- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-report`.
- [x] `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` are absent from `worker-ci-repair`.
- [x] Worker startup fail-closed guard against Gitea write tokens remains frozen by Slice 6D.2.

Safe inspection pattern (prints names only, never values):

```bash
cd /opt/ai-sdlc-lab/agent-control-plane
for service in worker-rlm-root worker-report worker-ci-repair; do
  docker compose -f docker-compose.ct104.yml exec -T "$service" sh -c \
    'for n in GITEA_BOT_TOKEN GITEA_AGENT_TOKEN; do [ -n "$(printenv "$n")" ] && echo "PRESENT:$n"; done' \
    </dev/null
done
```

Observed token-name output: empty for all three worker containers.  
Result: `PASS`

## D. Slice smoke — `V10_T005_SMOKE_OK`

- [x] `resolve_controller_backend()` default (no override) resolves to `deterministic` (C0 arm).
- [x] `resolve_controller_backend()` honours caller override to `model` (C1 arm selector).
- [x] `resolve_controller_backend()` honours `RECURSIVE_CONTEXT_CONTROLLER_BACKEND` env override.
- [x] Unrecognised backend values fall back to `deterministic` (fail-safe, no typo escalation).
- [x] Production yaml pin remains `controller_backend: deterministic` in `config/recursive_context.yaml`.
- [x] Platform-freeze amendment SHA `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` is present on deployed hosts.

Smoke marker: `V10_T005_SMOKE_OK`  
Result: `PASS`

## E. Regression floor

- [x] CT103 remains sole Gitea mutation authority; CT104 produces artifacts only.
- [x] No protected `main` mutation by agent path.
- [x] Publish still via CT103 `publish-broker` only.
- [x] Authority boundary unchanged: controller receives evidence references only; no repo write, network, or secret paths.

Result: `PASS`

## F. DEEPER_EVAL (non-blocking)

- [ ] Live C1 end-to-end against the real 2070 endpoint not yet scored in this deploy smoke. Unit tests exercised C0/C1 separation against a mocked gateway only.
- [x] Deferred to harness smoke in T02/T05: capture one live C1 run with `RECURSIVE_CONTEXT_CONTROLLER_BACKEND=model` (or `agentctl rlm run --controller-backend model`), recording resolved `controller_model_id`, token counts, and non-zero `controller_gpu_seconds` when the endpoint reports timings.

Result: `DEEPER_EVAL` (non-blocking for T00.5 deploy gate; does not block T01)

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697
smoke: V10_T005_SMOKE_OK
next_ticket_unblocked: yes (T01)
deeper_eval: live C1 end-to-end against real 2070 deferred to T02/T05 harness smoke
blocker: none
```
