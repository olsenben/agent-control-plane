# Deploy verification — VExp W1 (2026-08-19)

Copied from [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md).

## Identity

| Field | Value |
|-------|-------|
| Ticket ID | VExp W1 (0, A–F) |
| Slice docs | `docs/slice-vexp-w1-0-types.md`, `docs/slice-vexp-w1-a-lexical.md`, `docs/slice-vexp-w1-b-symbols.md`, `docs/slice-vexp-w1-c-graph.md`, `docs/slice-vexp-w1-d-builder.md`, `docs/slice-vexp-w1-e-eval.md`, `docs/slice-vexp-w1-f-workspace.md`, `docs/slice-vexp-w1-f-production.md` |
| Tip SHA (expected) | `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698` |
| Date (UTC) | 2026-08-19 |
| Operator | Cursor agent (W1 deploy verify) |
| maintenance-evals SHA | `f5a1c56c2d19c70aa49766d16cd0c577eb705e05` (local repo; no remote) |
| ADR | ADR-0038 (proposed) |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` (or equivalent) green for tip | pass (local) / Actions pending | W1 commit ruff-clean; local W1 tests in `tests/test_eval_context_mode.py` and provider tests. Live host smoke below. |
| `deploy` (CT103) green for tip | pass / N/A | push `35e155d..19db1f2` then SSH rebuild of `control-plane` / `worker-state` / `publish-broker` |
| `deploy-ct104` green for tip | pass / N/A | SSH rebuild of `docker-compose.ct104.yml` (`worker-rlm-root`, `worker-report`, `worker-ci-repair`) |

Local tests plus live CT103/CT104 smoke are the recorded truth for this gate. Gitea Actions run IDs were not scraped in this wave (same as W0).

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698` | yes |
| CT104 (`192.168.4.63`) | same | `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `status=ready`; `redis=ok`, `state_dir=ok`; local 3080 `ok` |
| Required compose services up | ok | CT103: control-plane, worker-state, publish-broker running. CT104: worker-rlm-root, worker-report, worker-ci-repair running. `CT104_RENDER_IMPORT_OK` |
| Unexpected secret / write-token on CT104 | absent | `CT104_GITEA_WRITE_FLOOR_OK` |

## D. Slice smoke (ticket-specific)

Fake-engine `local-deterministic` eval-dispatch on CT103 control-plane against `tests/fixtures/vexp_mini_repo` (exact-SHA git workspace copied into the container). Script: `scripts/_vexp_w1_deploy_verify.sh`.

| Step | Result | Evidence |
|------|--------|----------|
| `baseline_v1` v1 pack + hashes | pass | `sess-eval-cbdba96bd0e84f45b834ac656133a0c7`; `context_pack.v1`; pack `cfad6c2540734de31b66366702c2df1645ac5c0651de0e3b4d1db1783a5a41b2`; rendered `08bce9f1030a45164595e0a9a8ba0cbc79b2a8967927eadd77b23f05168a39dd`; `repair_attempts=0` |
| `context_v2_lexical` V2 lexical-only | pass | `sess-eval-bd30595e9fac47f7be267946e0b87f81`; `context-pack.v2`; providers `['lexical']`; `=== context-pack.v2 ===` in persisted user prompt; no `=== context_pack.v1 ===` |
| `context_v2` full providers | pass | `sess-eval-8b8623e155f54975998234a3dcf33edd`; providers `['lexical', 'symbol', 'graph']`; pack `ff34bf49ea65dfed7880667ec99a48ed9f794fc90ae1d4565f04b64b97224bc5`; rendered `c6db4c062a9b35954bf1da6247cdf51c3169d934f3e6c20b5806ef9ded7cbcf1` |
| Production default remains v1 | pass | `PROD_DEFAULT_COMPILE_CONTEXT_PACK_OK` (`CONTEXT_MODE=baseline_v1`, `compile_context_pack` still the typed path) |
| Production V2 exact-SHA workspace | pass | `PROD_EXACT_SHA_WORKSPACE_OK=0aee5c32a9f0583b2e31a53fe354b35387ba6ce9` (detached clone of the probe repo; not the graph branch-tip cache) |
| No scored freeze / reserved split | pass | W1 emitted no scored result set |

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass (retrieval-mode fake engine; no Gitea write) |
| Risk 2 still requires approval + sandbox when exercised | N/A (W1 did not exercise Risk 2) |
| Publish still via CT103 `publish-broker` only | pass / N/A (unchanged; CT104 write-token floor holds) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698
next_slice_unblocked: yes
blocker: none
```

Phase 4 (A vs B0 vs B1 DEV bakeoff) may open. Do not flip the production default. Do not treat this as a scored experiment. Memory/recursion/2070/repair remain off. V10 T08/T09 remain WaitingHuman on the V10 ledger.
