# Deploy verification — VExp W0 (2026-08-19)

Copied from [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md).

## Identity

| Field | Value |
|-------|-------|
| Ticket ID | VExp W0 (A–E) |
| Slice docs | `docs/slice-vexp-w0-a-repo-snapshot.md`, `docs/slice-vexp-w0-b-context-pack-v2.md`, `docs/slice-vexp-w0-c-verification-contract.md`, `docs/slice-vexp-w0-e-baseline-harness.md` |
| Tip SHA (expected) | `d39206d3c2184125e9af55eccdde58f6531bcca3` |
| Date (UTC) | 2026-08-19 |
| Operator | Cursor agent (W0 integration) |
| maintenance-evals SHA | `a6969f8` (local repo; no remote) |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` (or equivalent) green for tip | pass (local) / Actions pending | local: `ruff check .` clean; `pytest -q` **978 passed** in 619s; evals W0 tests **12 passed** |
| `deploy` (CT103) green for tip | pass / N/A | push `c5ccafe..d39206d` triggered workflows; hosts pinned by SSH rebuild |
| `deploy-ct104` green for tip | pass / N/A | SSH rebuild of `docker-compose.ct104.yml` |

Local pytest is the recorded test truth for this gate. Gitea Actions run IDs were not scraped in this wave.

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `d39206d3c2184125e9af55eccdde58f6531bcca3` | yes |
| CT104 (`192.168.4.63`) | same | `d39206d3c2184125e9af55eccdde58f6531bcca3` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | `redis=ok`, `state_dir=ok`. Overall JSON `degraded` from pre-existing OpenAI 401 probes and 2070 timeout. Local 3080 `ok`. |
| Required compose services up | ok | CT103: control-plane, publish-broker, redis, worker-state running. CT104: worker-rlm-root, worker-report, worker-ci-repair running. |
| Unexpected secret / write-token on CT104 | absent | `CT104_GITEA_WRITE_FLOOR_OK` |

## D. Slice smoke (ticket-specific)

| Step | Result | Evidence |
|------|--------|----------|
| Import `RepoSnapshot`, `ContextPackV2`, `ExperienceVerificationResult` in CT103 control-plane | pass | `W0_IMPORT_OK` |
| Fake-engine `local-deterministic` eval dispatch | pass | `sess-eval-e6daba83fd3a465494b512547339b9fa`; session nest did not expose `schema_version` (smoke limitation). Local golden comparison executed: render SHA-256 `ac1d350c663cd8daa128d46ac10b494b94ae43aad58bdaed77f704e1e2712bd1`. |
| Schema digest parity | pass | `f4bf354020903368fa3f5d0bec266dabc0b55f698ea23398b5bc21e1e8a4f1e0` |
| No scored freeze / reserved split | pass | W0 emitted no scored result set |

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Risk 2 still requires approval + sandbox when exercised | N/A (W0 did not exercise Risk 2) |
| Publish still via CT103 `publish-broker` only | pass / N/A (unchanged) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: d39206d3c2184125e9af55eccdde58f6531bcca3
next_slice_unblocked: yes
blocker: none
```

W1 may open. Do not treat this as a scored experiment. Do not scale compact-card memory. V10 T08/T09 remain WaitingHuman on the V10 ledger.
