# Deploy verification — VExp W1 treatment-exposure repair (2026-08-19)

Copied from [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md).

## Identity

| Field | Value |
|-------|-------|
| Ticket ID | VExp W1-TE (treatment-exposure repair) |
| Slice doc | `docs/slice-vexp-w1-treatment-exposure-repair.md` |
| Tip SHA (expected) | `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66` |
| Date (UTC) | 2026-08-19 |
| Operator | Cursor agent (W1-TE deploy verify) |
| maintenance-evals SHA | `5891c452c53e3b35627a33ddb0aedcc0ea47e895` (local-only) |
| ADR | ADR-0039 (proposed) |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` (or equivalent) green for tip | pass | Actions test jobs 931/932/933 on `7e51983`; local `test_treatment_exposure_pre_invocation.py` + W1/W0 eval tests |
| `deploy` (CT103) green for tip | pass | Actions deploy 934; run 940/941/942 success |
| `deploy-ct104` green for tip | pass | Actions deploy 935 |

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66` | yes |
| CT104 (`192.168.4.63`) | same | `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66` | yes |

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | rebuild completed; smoke ran inside control-plane |
| Required compose services up | ok | CT103: control-plane, worker-state, publish-broker. CT104: worker-rlm-root, worker-report, worker-ci-repair. `CT104_RENDER_IMPORT_OK` |
| Unexpected secret / write-token on CT104 | absent | `CT104_GITEA_WRITE_FLOOR_OK` |

## D. Slice smoke (ticket-specific)

Fake-engine eval-dispatch on CT103 plus a forced invalid-JSON / json-retry-timeout engine. Script: `scripts/_vexp_w1_deploy_verify.sh`.

| Step | Result | Evidence |
|------|--------|----------|
| `baseline_v1` v1 pack + hashes | pass | `sess-eval-80bcaf7e41d34bb79515ca1f8acd787a`; `context_pack.v1`; pack `af54600f…`; rendered `08bce9f1…`; `repair_attempts=0` |
| `context_v2_lexical` V2 lexical-only | pass | `sess-eval-c5f47cc212dd4b3380135d3f3dd97220`; providers `['lexical']`; V2 prompt present |
| `context_v2` full providers | pass | `sess-eval-0789502708304680b23605907ce271b8`; providers `['lexical', 'symbol', 'graph']`; pack `165887b5…`; rendered `910789cf…` |
| Forced parse + retry-timeout keeps V2 hashes | pass | `sess-eval-9ab2d3e0b3b24327bd271543b6c03487`; `evaluated_agent`; pack hash `7e285e9f…`; `SMOKE_parse_timeout_TREATMENT_OK` |
| Production default remains v1 | pass | `PROD_DEFAULT_COMPILE_CONTEXT_PACK_OK` |
| Production V2 exact-SHA workspace | pass | `PROD_EXACT_SHA_WORKSPACE_OK=0ecae22d55c9ea30ada4e27edb49b46072694fdb` |

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass (retrieval-mode fake engine; parse-timeout path does not apply a patch) |
| Risk 2 still requires approval + sandbox when exercised | N/A |
| Publish still via CT103 `publish-broker` only | pass / N/A (CT104 write-token floor holds) |

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: 7e51983ac5a3b9fa38a6176da99ff03cdda3ee66
next_slice_unblocked: no
blocker: none
```

Repair code landed in `f367bf05`. Follow-up `7e51983` excludes `tests/fixtures` from ruff so CT102 Lint matches local `ruff check .`. Hosts were rebuilt on `f367bf0` then fast-forwarded by Actions deploy to `7e51983`. WAVE 2 stays blocked: treatment exposure is complete on the repaired result set, but verified_success is at floor. Production default stays v1. Frozen `vexp-w1-context-v2-dev-v1` is immutable.
