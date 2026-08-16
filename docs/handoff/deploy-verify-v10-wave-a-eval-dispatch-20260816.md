# Deploy verification — V10 Wave A, `1.2.0-eval-dispatch`

| Field | Value |
|-------|-------|
| Ticket ID | V10-WAVE-A-1.2.0-eval-dispatch |
| Scope | Commit + deploy-verify the eval-dispatch engineering gate. No scored run |
| Tip SHA (ACP, verified) | `657a445d38e0b2a32970c7b6169e598883b33d06` |
| Prior deployed SHA | `e5d91ce29bd0c9d1f0f2c5ebd55a53988fe4d697` (V10 T00.5) |
| Runtime delta vs prior deploy | `src/agent_control/cli.py`, `src/agent_control/eval_dispatch.py` only |
| Evaluation repo SHA | `maintenance-evals@fb7bde1e58c4666f75c0182fd96bab9817e201d4` (local-only repo, no remote) |
| Experiment version | `1.2.0-eval-dispatch` |
| Date (UTC) | 2026-08-16 |
| Operator | V10 Wave A slice coordinator |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `ci.yaml` `test` for tip | **fail (pre-existing, unrelated)** | run 889 / job 1242 — failed step `Lint` |
| `deploy.yaml` (CT103) for tip | **fail at `Lint`, deploy step never reached** | run 891 / job 1245 |
| `deploy-ct104.yaml` for tip | **fail at `Lint`, deploy step never reached** | run 890 / job 1243 |

**Root cause, established not assumed.** `pyproject.toml` declares
`dev = [... "ruff>=0.4" ...]`, so CT102 installs whatever ruff is current — now
`0.16.3`, which enables rules the repo was never linted against. A clean checkout
of the tip reports **391 errors across the whole tree** under `0.16.3` and **zero**
under the repo's pinned `0.15.17`. The same `Lint` step passed on `2532de7`
(platform freeze) and `fa51ec8` and began failing at `d9dae98`, before any Wave A
work existed. Of the 391, only 2 are in Wave A code and both are stylistic
modernizations (`UP035` `Callable` import source, `UP017` `datetime.UTC` alias).

Because the pipeline could not run, CT103 and CT104 were deployed by host pin over
SSH and verified directly — the method used in V10 waves 2 and 4. Recommended
follow-up (not done here, it would touch the frozen platform): pin ruff in the dev
extra, then re-green CI in its own wave.

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `657a445d38e0b2a32970c7b6169e598883b33d06` | yes |
| CT104 (`192.168.4.63`) | same | `657a445d38e0b2a32970c7b6169e598883b33d06` | yes |

Method: WSL bash + `$HOME/.ssh/.ct103_deploy`; scripts
`scripts/_v10_wave_a_deploy_verify.sh`, `_v10_wave_a_recheck.sh`,
`_v10_wave_a_credfloor.sh`, `_v10_wave_a_snapshot.sh`.
CT103 rebuilt `control-plane`, `publish-broker`, `worker-state`;
CT104 rebuilt all three workers from `docker-compose.ct104.yml`.

## C. Control-plane health and config identity

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` | `degraded` — same class as before this deploy | `redis: ok`, `state_dir: ok`, `observe_public_base_url: configured` |
| Degradation cause | pre-existing | `model_2070` (`100.125.235.54:11434`) unreachable/timeout — the same missing live 2070 endpoint the ledger already tracks |
| CT103 compose services | ok | `control-plane`, `publish-broker`, `redis`, `worker-state` running |
| CT104 workers | ok | `worker-ci-repair`, `worker-report`, `worker-rlm-root` running |
| CT103 control-plane image | `sha256:c979a0ce1ef4…` | rebuilt at tip |
| CT104 worker images | `worker-ci-repair sha256:57db725fb744…`, `worker-report sha256:4ec53bf7d544…`, `worker-rlm-root sha256:8986494504e1…` | rebuilt at tip |
| `config/recursive_context.yaml` SHA-256 | `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` | unchanged, matches the T00.5 freeze pin |
| `docker-compose.yml` SHA-256 | `021d8b9df825e6f58393da401e314064bbb0e111862410c31ec3f16ecb66858f` | unchanged by this wave |

## D. Slice smoke

### D1. eval-dispatch entrypoint live on CT103 (in-container, non-scored)

Probe script copied into the `control-plane` container and run with
`docker compose exec -T … </dev/null`; a throwaway git workspace was created
inside the container and dispatched through the **fake** engine.

| Step | Result | Evidence |
|------|--------|----------|
| `agentctl eval dispatch` present in the deployed image | pass | single JSON object returned on stdout |
| Exact-SHA workspace accepted | pass | `session_id sess-eval-386aa90f97d8…` |
| Session record schema | pass | `maintenance_eval_session.v1`, `status=finished` |
| `agent_execution` | pass | `true` |
| Banner | pass | `V10_WAVE_A_EVAL_DISPATCH_OK` |

Finding: `control_plane_sha` recorded `0000…0` inside the container because the
image has no git checkout. The `CONTROL_PLANE_SHA` / `EVAL_CONTROL_PLANE_SHA`
override exists and must be set for any scored batch that dispatches in-container.
Harness runs from the repo checkout resolve the real SHA.

### D2. Longitudinal `--with-agent` smoke (host, non-scored)

`maintenance-evals/scripts/smoke_eval_dispatch_longitudinal.sh` — one episode,
both arms, all repeats, fake engine, create-only output.

| Step | Result | Evidence |
|------|--------|----------|
| Output directory | pass | `results/v10-t07b-longitudinal-de-agent-smoke-v1` |
| `experiment_version` | pass | `1.2.0-eval-dispatch` |
| `agent_execution=true` | pass | 6 of 6 slots |
| `scored` / `h3_claimed` | pass | `false` / `false` |
| `claim_scope` | pass | `h3_instrument_plus_agent_execution_no_h3_claim_until_scored_thresholds` |
| `unresolved_blockers` | pass | `[]` |
| Re-run result-set SHA-256 | recorded | `26974978be6556070c0c6a940399832d89d267b33768f11a844999f39bc1e452` |

The re-run replaced the committed smoke files: session ids and timestamps are
embedded, so the set hash differs run to run. Non-scored smoke artefacts are not
freeze-protected; the deploy-verify re-run is the version now in Git.

### D3. T07 instrument preservation (hard requirement)

| Check | Result | Evidence |
|-------|--------|----------|
| `results/v10-t07-longitudinal-de-v1/freeze.json` `result_set_sha256` | unchanged | `6f2fe30804e49be15c36e0d4070aeb4da6cbf51934ae2b457458a3cc0684fcc8` |
| Its `experiment_version` | unchanged | `1.1.0-t04-frozen` |
| Git status of the T07 directory | unmodified | not listed in `git status` after the smoke |

### D4. CT102

N/A. Wave A introduces no planning, repair, or deploy authority on CT102 and adds
no workflow. The only CT102 interaction was reading Actions run status. See section
A for the pre-existing pipeline failure.

## E. Regression floor

| Check | Result | Evidence |
|-------|--------|----------|
| No Gitea write token or password on CT104 | pass | only `GITEA_BASE_URL` and `GITEA_AGENT_COMMENT_ENABLED` present in all three workers |
| No state/Redis secret on CT104 | pass | `AGENT_STATE_TOKEN` / `STATE_API_TOKEN` / `REDIS_PASSWORD` absent in all three |
| CT104 sandbox workspace create/teardown | pass | git workspace created, committed and removed under `WORKSPACE_ROOT=/tmp`; `CT104_WORKSPACE_TEARDOWN_OK` |
| Publish still via CT103 `publish-broker` only | pass | service running; no publish-path change in the delta |
| No protected `main` mutation by the agent path | pass | dispatch commits only inside the caller-supplied workspace, `allow_push=false`, `allow_merge=false` |
| Policy / model routing unchanged | pass | `recursive_context.yaml` hash unchanged; no routing code in the delta |

**Deviation found (pre-existing, not introduced by Wave A):**
`MODEL_2070_EXTERNAL_API_KEY` and `MODEL_3080_EXTERNAL_API_KEY` are set on all
three CT104 workers with a real provider-shaped key (`sk-…`, identical value, 164
chars), and CT103 `/readyz` shows both external and fallback model checks resolving
to `https://api.openai.com/v1`. CT104's `.env` is dated 2026-07-21 and was not
touched by this wave. Wave A made no paid call — both smokes used the fake engine
and the dispatch path itself performs no frontier escalation. But a "local-only"
scored batch could fail over to a paid endpoint without a spend gate noticing, so
this must be resolved or explicitly frozen before Wave B scores anything. It is
already the routing confound named in `docs/THREAT_TO_VALIDITY.md`.

## Pre-commit verification (host)

| Check | Result |
|-------|--------|
| ACP `.venv/bin/ruff check .` | pass (ruff 0.15.17, exit 0) |
| ACP `pytest -q` | 905 passed |
| maintenance-evals ruff (committed surface) | pass |
| maintenance-evals `pytest -q` | 179 passed |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 657a445d38e0b2a32970c7b6169e598883b33d06
maintenance_evals: fb7bde1e58c4666f75c0182fd96bab9817e201d4
experiment_version: 1.2.0-eval-dispatch
scored_result_produced: no
t07_instrument_preserved: yes
next_wave_unblocked: yes (Wave B is a separate human-authorized decision)
caveats: CT102 pipeline red on a pre-existing unpinned-ruff drift (deploy applied by host pin);
         CT104 carries a pre-existing external model API key that must be resolved before scored runs
blocker: none
```
