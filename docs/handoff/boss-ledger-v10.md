# Boss ledger — V10 Maintenance Evaluation & Economic Bake-off

Epic supervisor state. Prior: [boss-ledger-v9.md](boss-ledger-v9.md) (complete). Epic: [boss-ledger-v10-maintenance-evaluation-revised.md](../boss-ledger-v10-maintenance-evaluation-revised.md). Plan: `.cursor/plans/v10_eval_bakeoff_30f4388b.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | V10 — Maintenance Evaluation & Economic Bake-off |
| **Baseline tip** | `4376ef4` live-certified; docs/tag SHA `2532de7` (`eval-baseline-2026-08`) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) + V10 plan dual-freeze discipline |
| **Integration branch** | `main` |
| **Epic status** | **running** — recursive-policy Stage A frozen `INSUFFICIENT_SIGNAL` (`1.7.0-deeper-eval-recursive-policy-nonscored`); H3 unclaimed; scored H3 not started |
| **Tickets done** | 10 / 12 (T08 and T09 remain WaitingHuman); **3 / 5 hypotheses decided** (H1a UNDECIDED, H1b FAIL, H1c FAIL) |
| **Next ticket** | Open scored-H3 experiment version `1.6.0-h3-longitudinal-scored`, enable explicit `scored=true`, freeze it, then execute full D/E batch. Do not Stage B. Do not inspect val/test. Do not start T08. Do not execute scored H3 in this seal. H3 handoff remaps off 054. |
| **Latest handoff** | [054](coordinator-handoff-054.md) |
| **Last boss action** | 2026-08-18 — recursive-policy Stage A frozen `INSUFFICIENT_SIGNAL`; stop before Stage B / scored H3 |

## Wave A completion (`1.2.0-eval-dispatch`)

| Field | Value |
|---|---|
| ACP commit / deployed SHA | `657a445d38e0b2a32970c7b6169e598883b33d06` (pushed; CT103 + CT104 pinned); tip since advanced to `bb1dde3` by docs-only seal commits |
| `maintenance-evals` commits | `fb7bde1` (eval-dispatch harness) on `886c970` (corpora clearance), tip `f2ae2d3` (deploy-verify smoke re-run); repo has no remote |
| Deploy verify | [deploy-verify-v10-wave-a-eval-dispatch-20260816.md](deploy-verify-v10-wave-a-eval-dispatch-20260816.md) — **PASS** |
| Smoke | `results/v10-t07b-longitudinal-de-agent-smoke-v1` — `agent_execution=true` 6/6, `scored=false`, `h3_claimed=false` |
| T07 instrument | preserved: `6f2fe308…` under `1.1.0-t04-frozen` |
| Scored result | none; 0/5 hypotheses decided; 0 paid calls |
| Carried findings | CT102 CI red on unpinned-ruff drift (pre-existing); CT104 holds a real external model API key (pre-existing) — resolve before any scored batch |
| **Lanes** | main only |
| **Env** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; `docker compose exec -T … </dev/null` |

## Wave B completion (official H1 verifier bindings)

| Field | Value |
|---|---|
| `maintenance-evals` commit | `931153ba63e41da762e282cebb5d7b73f6f17d06` (repo has no remote) |
| ACP | unchanged; deploy verify **N/A** (no ACP source touched) |
| `SWE_CI_TASK_TEST_COMMAND` | **bound** -> upstream `run_pytest`, `swe-ci-default@b2a0620f` `src/swe_ci/benchmark/tools.py` (sha256 `d1810aed…`) |
| `ARB_TRAJECTORY_EVALUATOR` | **bound** -> `arb eval-trajectories`, `arb-v2@07014c98` `src/agent_retrieval_bench/trajectory.py` (sha256 `c5995d46…`), dist `agent-retrieval-bench` 0.2.1 |
| Record | `manifests/benchmarks/verifier-bindings.yaml` (`benchmark_verifier_bindings.v1`); narrative `docs/VERIFIER_BINDINGS.md` |
| DEV smoke | ARB **pass** (2 dev samples × 2 arms, discriminates 1.0 vs 0.0); SWE-CI **pass** (1 dev task, 943→957, gap 14 matches upstream metadata); `scored=false`, 0 hypotheses claimed |
| Harness corrections | 5, all `semantics_changed: false`: SWE-CI `--instance` does not exist; official/additional command lists swapped; "ANC" is not an upstream key; ARB passed 4 flags `eval-trajectories` rejects; ARB metric names were snake_case renames of the *ranking* family |
| Versions | `arb-adapter-1.1.0`, `swe-ci-adapter-1.1.0`, registry `1.1.0-official-bindings` (digest `3099cdba…`); 5 experiment manifests resealed |
| Splits / seeds / frozen_groups | **unchanged**; a test recomputes both assignments from materialization evidence and asserts equality across the bump |
| Deliberately unbound | ARB ranking family (`MRR`, `Recall@k`, `gold_coverage@8k`, `selective_success@20`) — no V10 arm produces a corpus-wide ranking; ARB results are **not** comparable to ranking leaderboards |
| Gates | 199 tests + ruff green on the committed surface; ACP ruff green |
| Scored result | none; 0/5 hypotheses decided; 0 paid calls |

## Wave C completion (live C1 proof attempt — FAIL, non-scored)

| Field | Value |
|---|---|
| Handoff | [048](coordinator-handoff-048.md) |
| ACP commits | `0951e56` (C1 local-only + timing truth), `027ad9f` (model-id provenance); both pushed |
| Deployed tip | `027ad9f06328f9b55f217b042d14c2fcb2beb25d` on CT103 **and** CT104; docs tip since advanced by docs-only seal commits (`b491b6e`, `1b9be38`, `ca657a1`) |
| Deploy verify | [deploy-verify-v10-wave-c-20260816.md](deploy-verify-v10-wave-c-20260816.md) — **PASS** |
| **`c1_proof`** | **FAIL** — `controller_model_invoked=false` |
| Cause | RTX 2070 host `msi` (`100.125.235.54`) offline, `last seen 12h ago`; ping no reply; LAN sweep finds no alternate `:11434` |
| Contamination | **none** — one candidate route, local `gpu`/`qwen2.5-coder:3b`; `controller_data_left_homelab=false`; 0 external routes offered; 0 paid calls |
| Live evidence | `docs/evidence/v10-wave-c/c1-live-smoke-027ad9f.json` |
| Negative control | **PASS on both hosts** — forced OpenAI-only candidate refused, `external_route_refused`, zero external HTTP attempts (`c1-negative-control-027ad9f.json`) |
| Boundary now enforced | provider must be `gpu` **and** host must be loopback / RFC1918 / `100.64.0.0/10` / `.ts.net`; refusal happens before any request is sent |
| Timing truth | `controller_gpu_seconds` is nullable; unreported metrics land in `controller_missing_fields`; no fake `0.0` |
| Model-id truth | `controller_model_id` now prefers the endpoint-reported model; `controller_model_id_source` ∈ `endpoint_reported` / `configured` / `planned_not_invoked`. Handoff 035 decision 3 was wrong — the configured name used to always win |
| Freeze | `config/recursive_context.yaml` untouched (`8258dc95…`); no amendment; no change to prompt, role, budgets, sampling, recursion trigger, tool policy, or Qwen identity |
| **New finding** | CT103 `MODEL_2070_NAME=qwen2.5-coder:3b` vs CT104 `qwen2.5-coder:7b` against the *same* endpoint — the 2070 identity is not frozen; gate G7 blocker for any C1 batch. Not fixed here (it is the C1 evaluated identity) |
| Gates | 920 tests + `ruff check .` green |
| Scored result | none; 0/5 hypotheses decided; 0 paid calls; H1c still unclaimed |
| Carried findings | CT104 provider key present on all three workers (gate 6, now unusable by C1); CT102 ruff drift |

## Wave C retry (live C1 proof — PASS, non-scored)

| Field | Value |
|---|---|
| Handoff | [049](coordinator-handoff-049.md) |
| Prior FAIL | [048](coordinator-handoff-048.md) + `c1-live-smoke-027ad9f.json` — **not overwritten** |
| Deployed tip | still `027ad9f06328f9b55f217b042d14c2fcb2beb25d` (env-only host alignment; no ACP source change) |
| Deploy verify | **N/A** — no ACP image/code change; CT103 `control-plane` recreated to pick up `.env` |
| Frozen identity | `MODEL_2070_NAME=qwen2.5-coder:7b` digest `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` |
| Host alignment | CT103 `.env` `:3b` → `:7b`; CT104 already `:7b`; both request `http://100.125.235.54:11434` |
| ACP-host tags on 2070 URL | only `qwen2.5-coder:7b` (human localhost `:14b`/`llama3` were the 3080 on `buttholecentral`) |
| **`c1_proof`** | **PASS** |
| `controller_backend` | `model` |
| `controller_model_invoked` | `true` |
| `controller_model_id` | `qwen2.5-coder:7b` (`controller_model_id_source=endpoint_reported`) |
| `controller_provider` | `gpu` |
| `controller_data_left_homelab` | `false` |
| `controller_route_class` | `direct_local` |
| `controller_external_routes_refused` | `0` |
| Tokens | prompt 160 / completion 110 |
| GPU seconds | `null` + `missing_fields=["controller_gpu_seconds"]` (not fake `0.0`) |
| Contamination | **none** — one candidate `gpu`/`qwen2.5-coder:7b`; not gpt-4.1 / gpt-4o-mini |
| Live evidence | `docs/evidence/v10-wave-c/c1-live-smoke-049-qwen7b.json` |
| Freeze amendment | [v10-wave-c-2070-identity-freeze-amendment.md](v10-wave-c-2070-identity-freeze-amendment.md) |
| Scored result | none; 0/5 hypotheses decided; 0 paid calls; H1c still unclaimed (proof only) |

## Wave D completion (scored H1 DEV — frozen)

| Field | Value |
|---|---|
| Handoff | [051](coordinator-handoff-051.md) (prior blocker: [050](coordinator-handoff-050.md)) |
| Experiment version | `1.3.0-h1-dev-scored` @ `maintenance-evals@ea71ede` |
| Result set | `results/v10-h1-dev-scored-v2` digest `13ba38d5fa72b38a73d65d36b2b334feb3ed4a50da1c379491dc969450247685` |
| Slots | **612/612** frozen; `scored=true`; split `dev` |
| ACP deployed | still `c5ccafe` (arm-aware eval-dispatch `9447c1c` + ADR-0034); no ACP source this turn |
| Deploy verify | **N/A** this turn (no ACP image/code change); prior arm-wiring record [deploy-verify-v10-wave-d-20260816.md](deploy-verify-v10-wave-d-20260816.md) |
| **`scored`** | **yes** — `--decide-only` applied after freeze |
| H1a / H1b / H1c | **UNDECIDED / FAIL / FAIL** (ARB 43 tasks / 6 clusters; Holm family) |
| `h1_selected_local_strategy` | **not written in Wave D** (sealed later in handoff 052 as operational B) |
| Arms | A,B,C0,C1 valid; B ≠ A (`rg` present); C1 never invoked; 3080 not used as C1 |
| SWE-CI | 96/96 harness-excluded (`No module named 'swe_ci'`); H1 is ARB-DEV only |
| Contamination | none |
| val/test | not inspected |
| v1 | not interpreted (still invalid audit) |
| Second batch | not started |
| Carried | CT104 external key; CT102 ruff drift |

## Pre-Wave-E SWE-CI repair (scored H1 supporting — frozen)

| Field | Value |
|---|---|
| Handoff | [052](coordinator-handoff-052.md) |
| Experiment version | `1.4.0-h1-sweci-repair` (parent `1.3.0-h1-dev-scored`) |
| Result set | `results/v10-h1-dev-scored-v3` digest `5db3c0f781b1e4a823bab6579478968fb0e8b1278d4eba4b1e4c2b46c6f4b5ae` |
| Slots | **96/96** SWE-CI DEV only; `scored=true`; A/B/C0/C1 = 24 each |
| v2 | **unchanged** digest `13ba38d5…247685`; ARB not rerun |
| Repair | isolated Wave B python; ACP `.venv` not pip-installed; `semantics_changed: false` |
| Valid / harness | 96 valid, **0 harness**, 0 infra, 11 evaluated_agent |
| Official / additional | official_benchmark_pass false 96/96; v10 additional true 96/96 |
| C1 invoke | **0/24** (`controller_model_invoked=false`) |
| Canonical H1a/H1b/H1c | **UNDECIDED / FAIL / FAIL** (v2 ARB; not rewritten) |
| Supporting SWE-CI H1 | FAIL / FAIL / UNDECIDED (wall ~2.6s; not pooled; cannot overturn) |
| `h1_selected_local_strategy` | `local-deterministic` / `operational_selection_not_hypothesis_pass` |
| Gate 6 | CT104 external keys **ABSENT** (revoked 2026-08-17) |
| val/test | not inspected |
| Wave E | **done** (handoff 053) |
| Contamination | none |

## Wave E completion (H1 operational inherit — frozen)

| Field | Value |
|---|---|
| Handoff | [053](coordinator-handoff-053.md) |
| Experiment version | `1.5.0-wave-e-h1-inherit` (runtime parent `1.2.0-eval-dispatch`) |
| `maintenance-evals` | `e4a85c215c2a8347243840f600aecbf517671ef6` (parent `650c8dbb2d15c9255ddbea865773b8b9b296376c`) |
| ACP | unchanged at `b87b19c267c7c3e84801f5726ad03e78df463300` (052); deploy verify **N/A** |
| Inherit artifact | `manifests/inheritance/v10-wave-e-h1-inherit.json` |
| `h1_selected_local_strategy` | `local-deterministic` / `operational_selection_not_hypothesis_pass` |
| Canonical H1a/H1b/H1c | **UNDECIDED / FAIL / FAIL** (v2 ARB; not rewritten) |
| D | `local-deterministic` + memory reset |
| E | `local-deterministic` + `preserve_verified` |
| H | `local-deterministic` local stage via inherit artifact; frontier YAML still `1.1.0-t04-frozen` |
| `model_2070_required` | **false** |
| Smoke | `results/v10-wave-e-de-inherit-smoke-v1` digest `a49c992c986669810ce576cd10652ca38bed4231818b4ced6a39f633aa878906` |
| Slots | 4: retry-toolkit-e01/e02 × D/E × r1; fake engine; `agent_execution=true`; `scored=false` |
| Memory | E e01 admitted `mem-45b4a5c453f376978f314797`; E e02 retrieved that id; D consume 0 |
| Tests | pytest 60 passed (inherit/longitudinal/hybrid/e2e); ruff clean |
| v2 / v3 | **unchanged** digests `13ba38d5…247685` / `5db3c0f7…c6f4b5ae` |
| val/test | not inspected |
| H3 | **unclaimed**; `1.6.0-h3-longitudinal-scored` not created and not executed |
| Recursive-policy | Stage A frozen `INSUFFICIENT_SIGNAL` (handoff 054); Stage B not authorized |

## Recursive-policy Stage A (DEEPER_EVAL, non-scored — frozen)

| Field | Value |
|---|---|
| Handoff | [054](coordinator-handoff-054.md) |
| Experiment version | `1.7.0-deeper-eval-recursive-policy-nonscored` |
| Defining SHA | `maintenance-evals@8571fa7` (harness); freeze/docs `@d6e17549a723480bcf3a4be38c1fac5a83eb8e7d` |
| Result set | `results/v10-deeper-eval-recursive-policy-v1` digest `2850d7a412322f26d5862ee97d04496f7a6e4f7619a16bcb03496682963005b8` |
| Gate | **INSUFFICIENT_SIGNAL** (`P+_yield_pos=0/43`); `stage_b_authorized=false` |
| Tasks | ARB DEV 43; `scored=false`; 2070 not invoked |
| P1 | 34/43 triggered (`deterministic_fts_empty`); yield 0 |
| Bq vs B | identical hit counts 43/43 (13 JSON-wrapped) |
| C0-shadow | hermetic (`backend_io=false`) |
| Canonical H1a/H1b/H1c | **UNDECIDED / FAIL / FAIL** (v2 ARB; not rewritten) |
| H3 | **unclaimed**; `1.6.0-h3-longitudinal-scored` not created |
| `h3_planned_handoff_collision` | `054` (H3 remaps to next free id) |
| ACP | unchanged at `67836a1`; deploy verify **N/A** |
| val/test | not inspected |
| ADR | [ADR-0035](../adr/0035-eval-only-recursive-policy-bakeoff-stays-out-of-acp.md) proposed (eval-only; no production port) |

## Dual freezes

```text
T00/T00.5 = platform freeze
T04       = experiment freeze (docs/handoff/v10-experiment-freeze.md + tag)
T05+      = scored evaluation (no scored runs before experiment freeze)
```

## Spine (strict sequential)

```text
T00 -> T00.5 -> T01 -> T02 -> T03 -> T04 -> T05 -> T06 -> T07 -> T08 -> T09 -> T10
```

One implementation ticket per wave. No T07∥T08.

## Ticket states

`Ready | Running | Done | WaitingHuman | BlockedTechnical | InvalidExperiment`

## Tickets

| ID | Slice | Deps | Status | Tip |
|----|-------|------|--------|-----|
| **T00** | Platform baseline freeze + stale-doc reconciliation | — | Done | `4376ef4` live baseline; docs/tag `2532de7` (`eval-baseline-2026-08`) |
| **T00.5** | C0/C1 controller_backend truth | T00 | Done | `e5d91ce` |
| **T01** | maintenance-evals schemas/manifests | T00.5 | Done | `maintenance-evals@e9269e4` |
| **T02** | exact-SHA replay runner + evalctl | T01 | Done | `maintenance-evals` working tree; coordinator commit pending |
| **T03** | cost/usage telemetry + pricing | T02 | Done | `maintenance-evals` working tree; coordinator commit pending |
| **T04** | Benchmark methodology + adapters + EXPERIMENT_FREEZE | T03 | Done (WaitingHuman external licences/frontier pricing) | `maintenance-evals@b282f6d`; tag `v10-experiment-freeze-2026-08-16` |
| **T05** | A/B/C0/C1 block-randomized context ablation | T04 | Done (harness); WaitingHuman official ARB/SWE-CI H1 | result set `836086c8…` |
| **T06** | SWE-CI + SWE-Chain local E2E | T05 | Done (harness); WaitingHuman official SWE-CI/SWE-Chain | batch `1750165e…`; provisional C0 only |
| **T07** | Longitudinal D/E | T06 | Done (real batch + freeze); H3 unclaimed pending agent execution | `maintenance-evals@002fdc0`; result set `6f2fe308…` |
| **T08** | Frontier F/G | T06 | WaitingHuman (harness); blocker `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` + credentials/spend cap | `maintenance-evals` working tree |
| **T09** | Hybrid H + held-out | T08 | WaitingHuman (harness); blockers `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` + `MATERIALIZE_LICENSED_CORPORA` + credentials/spend cap | `maintenance-evals` working tree |
| **T10** | Frozen analysis + lit synthesis + go/no-go | T09 | Done (partial analysis on frozen partial evidence); epic remains `blocked_waiting_human` | `maintenance-evals` working tree; coordinator commit pending |

## Hypothesis status (authoritative)

```text
H1a UNDECIDED - frozen v2 DEV; t1_8pp_success met (+20.9pp B vs A) but Holm
                does not survive (p=0.171875, p_holm=0.515625). Not PASS.
H1b FAIL      - C0 vs B verified_success_diff=0.0; no threshold met
H1c FAIL      - C1 vs C0 no incremental benefit; C1 invoked 0/153;
                GPU-ran is not a win. Wave C live proof (049) still stands
                as non-scored routing evidence, not an H1c PASS.
H2  unclaimed - WaitingHuman FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE + credentials + spend cap
H3  instrument verified (T07); Wave E inherit frozen under `1.5.0-wave-e-h1-inherit` (non-scored smoke only); recursive-policy Stage A frozen `INSUFFICIENT_SIGNAL` under `1.7.0` (handoff 054, not H3); outcome still unclaimed until scored `1.6.0-h3-longitudinal-scored` thresholds
```

H1 scientific verdicts remain v2 ARB DEV (43 paired tasks). SWE-CI DEV was
repaired under `1.4.0-h1-sweci-repair` (96 valid, 0 harness) and is supporting
coverage only. `h1_selected_local_strategy` is `local-deterministic` with
`operational_selection_not_hypothesis_pass`. The T06 provisional
`local-recursive-fallback` / `PROVISIONAL_NOT_FOR_H2` is superseded for Wave E
inheritance. v1 staging is not evidence.

## Open human gates before any scored batch

```text
1. MATERIALIZE_LICENSED_CORPORA — CLEARED 2026-08-16
   (ARB 427 / SWE-CI 100 / SWE-Chain 155; evidence under
   maintenance-evals/evidence/materialization/; raw corpora outside Git)
2. EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS — CLEARED 2026-08-16
   (generic ACP maintenance_eval_dispatch.v1; experiment_version 1.2.0-eval-dispatch;
    T07 instrument preserved; H3 claim still requires scored agent batch)
3. FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE + credentials + spend cap -> unlocks H2
4. Live C1 observation against the real 2070 endpoint -> CLEARED 2026-08-16
   (Wave C retry / handoff 049). Non-scored smoke PASS:
   controller_model_invoked=true, endpoint-reported qwen2.5-coder:7b,
   provider=gpu, data_left_homelab=false. Evidence:
   docs/evidence/v10-wave-c/c1-live-smoke-049-qwen7b.json. Does not score H1c.
5. Decide H1 on dev — CLEARED 2026-08-17 (handoff 051) and sealed for
   Wave E inherit on 2026-08-18 (handoffs 052 then 053): H1a UNDECIDED, H1b FAIL,
   H1c FAIL on frozen v2. Operational inherit is `local-deterministic`
   (`operational_selection_not_hypothesis_pass`) frozen into D/E/H under
   `1.5.0-wave-e-h1-inherit`. Do not inspect val/test.
6. CT104 external model API key — CLEARED 2026-08-17: both
   `MODEL_*_EXTERNAL_API_KEY` removed from CT104 host `.env` and all three
   workers; re-proved ABSENT. Evidence:
   `docs/evidence/v10-h1-sweci-repair/gate6-cleared.json`.
7. FREEZE_2070_MODEL_IDENTITY — CLEARED 2026-08-16 (boss decision + host
   alignment). Frozen name `qwen2.5-coder:7b`, digest `dae161e2…`. CT103
   aligned to CT104. T00/T04 `:3b` kept as history; amendment in
   v10-wave-c-2070-identity-freeze-amendment.md. Handoff 048 not rewritten.
```

Official H1 verifier bindings are **no longer a gate**: both were bound and
DEV-smoked non-scored in Wave B. ARB's ranking metric family remains
permanently unbound by design, which constrains what H1 may claim rather than
blocking it.

## Hard gates

G1 trust-boundary · G2 C0/C1 telemetry truth · G3 platform freeze · G4 experiment freeze · G5 no leakage · G6 verification authority · G7 comparable arms · G8 cost traceability · G9 no silent tuning · G10 negative-transfer visibility · G11 infra separated · G12 full provenance · dual official/V10 metrics · seeded block-randomized order

## Wave log

| Wave | Date | Handoff | Next | Notes |
|------|------|---------|------|-------|
| 0 | 2026-08-16 | — | T00 | Ledger opened |
| 1 | 2026-08-16 | [034](coordinator-handoff-034.md) | T00 (deploy-verify) | Five stale CT104 write-token docs reconciled; repository-known baseline and live-cert checklist prepared; T00 remains Running with tip/tag/deploy fields TBD |
| 2 | 2026-08-16 | [034](coordinator-handoff-034.md) | T00.5 | `DEPLOY_VERIFY: PASS`; CT103+CT104 tip `4376ef4`; CT104 write tokens absent in all three workers; CT103 token/publish flag expected; image/model/Ollama inventory frozen; docs-only commit/tag SHA pending; CT102 runner version deferred to `DEEPER_EVAL` |
| 3 | 2026-08-16 | [035](coordinator-handoff-035.md) | T00.5 (deploy-verify) | `controller_backend` C0/C1 arm implemented; default stays `deterministic`; C1 routes `call_primary_model` to the `summarizer`/`MODEL_2070_*` role and fails soft; G2 telemetry on artifact, event, trajectory, CLI; `config/recursive_context.yaml` re-pinned `d438a2ee`→`8258dc95` with T00.5 freeze amendment; T00 final tagged SHA `2532de7` recorded; full tests + ruff green; T00.5 stays Running until deploy verification |
| 4 | 2026-08-16 | [035](coordinator-handoff-035.md) | T01 | `DEPLOY_VERIFY: PASS`; CT103+CT104 tip `e5d91ce`; `/readyz` ready; `V10_T005_SMOKE_OK` (`resolve_controller_backend` default/override); CT104 no Gitea write tokens; live C1 end-to-end against real 2070 deferred `DEEPER_EVAL` to T02/T05 harness smoke |
| 5 | 2026-08-16 | [036](coordinator-handoff-036.md) | T02 | T01 created evaluation-only `maintenance-evals` repo at `e9269e4` with frozen typed/schema contracts, four pre-registration manifests, dual verification metrics, scored failure taxonomy, methodology, and green tests; deploy N/A |
| 6 | 2026-08-16 | [037](coordinator-handoff-037.md) | T03 | T02 added exact-SHA isolated workspaces, immutable replay audit records, injectable trusted control-plane dispatch, terminal AgentSession/result-SHA/verification collection, failure separation, seeded block-randomized ordering, and `evalctl run/replay/validate-run`; 11 tests + ruff green; deploy N/A |
| 7 | 2026-08-16 | [038](coordinator-handoff-038.md) | T04 | T03 normalized session/trajectory local, recursive-controller, frontier, wall-time, attempts, and CI telemetry without zero-filling; added source/missing-field provenance, separate local GPU seconds, versioned pricing SHA provenance, Decimal paid-API calculation, explicit unknown usage/price statuses, cost-accounting docs, and tests; 16 tests + ruff green; deploy N/A |
| 8 | 2026-08-16 | [039](coordinator-handoff-039.md) | T05 | T04 sealed benchmark registry, adapters, splits, custom longitudinal corpus, manifests, and statistical plan under `v10-experiment-freeze-2026-08-16`; official external corpora remain WaitingHuman |
| 9 | 2026-08-16 | [040](coordinator-handoff-040.md) | T06 | T05 implemented frozen A/B/C0/C1 block scheduling at seed `20260815`, fail-closed official scoring, C0/C1 telemetry checks, and a create-only 24-slot synthetic harness result freeze (`scored=false`, no H1 claim); official ARB/SWE-CI H1 remains WaitingHuman |
| 10 | 2026-08-16 | [041](coordinator-handoff-041.md) | T07 | T06 implemented benchmark/task/repeat block scheduling, required E2E telemetry and leakage guards, separate 24-slot SWE-CI/SWE-Chain synthetic freezes, and a harness-only `local-recursive-fallback` selection labeled `PROVISIONAL_NOT_FOR_H2`; official success rates remain unclaimed and WaitingHuman |
| 11 | 2026-08-16 | [042](coordinator-handoff-042.md) | T08 | T07 built the reusable-memory store, hash-chained audit ledger, phase-split validity semantics and frozen D/E suite, then really executed 108 slots over the 18 dev+validation episodes: both arms saw the same 135 eligible records with D consuming 0 and E 135, `future_commits_reachable` 0 in 108/108, 42 stale retrievals retained, and 3/3 trap variants passing the official check while failing the frozen additional checks. H3 is recorded as unclaimed, not null, because no slot reached the frozen patch-authoring agent; blocker `EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS`. Test split untouched for T09 |
| 12 | 2026-08-16 | [043](coordinator-handoff-043.md) | T09 (orchestrator) | T08 added `frontier_spend` gates, F/G suite scaffolding in `suites/frontier_hybrid.py`, synthetic harness driver, and `docs/FRONTIER_CREDENTIALS.md`. Spend-cap hooks refuse without `frontier_id`, provider credentials, and total spend cap. Synthetic harness freeze only; no paid calls. T08 WaitingHuman on `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE`; not Done. T09 dep on T08 — orchestrator decides next |
| 13 | 2026-08-16 | [044](coordinator-handoff-044.md) | T10 | T09 added `hybrid_route.py`, `held_out.py`, `suites/hybrid_h.py`, `v10-hybrid-held-out.yaml`, synthetic harness freeze (`e3eba0ed…`, 15 slots), and `docs/HYBRID_H_HELD_OUT.md`. Route stub: preflight→local Qwen→conditional recursive→verify→typed frontier escalate; refuses paid escalation without credentials. Held-out test split reserved (config-loader, text-normalizer since T07). No paid or official scored batches. T09 WaitingHuman; not Done. T10 may proceed on frozen partial evidence |
| 14 | 2026-08-16 | [045](coordinator-handoff-045.md) | none (human gates) | T10 analyzed the six frozen result sets and sealed handoffs 034–044 and produced `reports/V10_RESULTS.md`, `docs/THREAT_TO_VALIDITY.md`, `docs/GO_NO_GO.md`, `reports/DEEPER_EVAL.md`, and `reports/LITERATURE_COMPARISON.md`. Zero of five hypotheses decided; no threshold evaluable; no primary test run. Go/no-go decision is **HOLD** — epic §32 branches A–E are all unavailable on evidence, branch B is closest and still unearned. Literature verified against arXiv:2607.24882, 2603.03823, 2605.14415, 2506.09289 and the SWE-bench ICLR 2024 lineage; a metric-naming defect was found (V10's frozen "ANC" is EvoScore at γ=1, discarding the paper's future weighting). Epic status set to `blocked_waiting_human` |
| 15 | 2026-08-16 | — | human gates | Cleared `EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS`: ACP `agentctl eval dispatch` (`maintenance_eval_dispatch.v1`), harness `--with-agent`, experiment version `1.2.0-eval-dispatch`; smoke `results/v10-t07b-longitudinal-de-agent-smoke-v1` (6/6 `agent_execution=true`); T07 `result_set_sha256` `6f2fe308…` unchanged; H3 still unclaimed |
| 16 | 2026-08-16 | [046](coordinator-handoff-046.md) | Wave B | Wave A sealed. Commits: `maintenance-evals@886c970` corpora, `fb7bde1` harness, ACP `657a445` eval dispatch (pushed). `DEPLOY_VERIFY: PASS` on `657a445`; smoke 6/6; T07 `6f2fe308…` preserved. Findings: CT102 ruff drift; CT104 pre-existing external model API key |
| 17 | 2026-08-16 | — | Wave B Running | Boss advance: bind SWE_CI_TASK_TEST_COMMAND + verify/bind ARB_TRAJECTORY_EVALUATOR; DEV-only non-scored smokes; no H1 scored batch |
| 18 | 2026-08-16 | [047](coordinator-handoff-047.md) | Wave C (human gate first) | Wave B sealed at `maintenance-evals@931153b`; ACP untouched, deploy N/A. Both official H1 verifiers are now commands, not names: `SWE_CI_TASK_TEST_COMMAND` -> upstream `run_pytest` (`swe-ci-default@b2a0620f`), `ARB_TRAJECTORY_EVALUATOR` -> `arb eval-trajectories` (`arb-v2@07014c98`), recorded in `manifests/benchmarks/verifier-bindings.yaml`. DEV smoke pass on both, non-scored: ARB discriminated 1.0 vs 0.0 on two samples with a negative control; SWE-CI reproduced upstream's declared 14-test gap (943→957) with the executed argv captured rather than predicted. Materialization exposed 5 harness mismatches in never-executed T04 command strings (`--instance` does not exist; 4 ARB flags rejected by the subcommand; both frozen metric name sets wrong) — all corrected, versioned to `arb/swe-ci-adapter-1.1.0` and registry `1.1.0-official-bindings`, splits/seeds/frozen_groups untouched and test-enforced. ARB's ranking family (`MRR`, `Recall@k`, `gold_coverage@8k`) deliberately left unbound. 199 tests + ruff green. 0/5 hypotheses decided; 0 paid calls; CT102 ruff drift and CT104 model key still open |
| 19 | 2026-08-16 | — | Wave C Running | Boss advance: prove live C1 against the real 2070, non-scored; CT104 external key must not answer the C1 controller call |
| 20 | 2026-08-16 | [048](coordinator-handoff-048.md) | none — WaitingHuman on 2070 power-on | Wave C **FAIL on `c1_proof`**: `msi` offline. Contamination path closed. MODEL_2070_NAME divergence 3b vs 7b left for human. |
| 21 | 2026-08-16 | — | Wave C Running | Human resume: 2070 Ollama tags = `qwen2.5-coder:14b`, `qwen2.5-coder:7b`, `llama3:latest`. Freeze C1 to `qwen2.5-coder:7b`; align CT103; do not use `:14b` or `:3b`. Re-run non-scored C1 smoke. |
| 22 | 2026-08-16 | [049](coordinator-handoff-049.md) | Wave D unstarted | Wave C retry **PASS on `c1_proof`**. ACP-host `/api/tags` on configured `msi` (`100.125.235.54:11434`) serves only `qwen2.5-coder:7b` (digest `dae161e2…`); human localhost `:14b`/`llama3` were the 3080 on `buttholecentral`. CT103 `.env` aligned `:3b`→`:7b`; CT104 already `:7b`. Live smoke `c1-live-smoke-049-qwen7b.json`: `controller_backend=model`, `controller_model_invoked=true`, `controller_model_id=qwen2.5-coder:7b` `endpoint_reported`, `provider=gpu`, `data_left_homelab=false`, `route_class=direct_local`, `external_routes_refused=0`, tokens 160/110, `gpu_seconds=null`+missing_fields, `scored=false`. Contamination none. ACP code unchanged; deploy N/A. Freeze amendment recorded; 048 FAIL left intact. 0 paid calls; H1c still unclaimed. |
| 23 | 2026-08-16 | [050](coordinator-handoff-050.md) | Wave D WaitingHuman | Wave D **not scored**. v1 28/612 staging invalidated (no `rg`; empty retrieval; 2070 down). Harness `1.3.0-h1-dev-scored` ready; next dir `v10-h1-dev-scored-v2`. `msi` offline again (CT103 curl timeout). H1a/H1b/H1c unclaimed. Wave E not started. 0 paid calls. |
| 24 | 2026-08-17 | [051](coordinator-handoff-051.md) | Wave E (not started) | Wave D **scored**. v2 612/612 frozen digest `13ba38d5…`. Decide-only: H1a UNDECIDED, H1b FAIL, H1c FAIL. Arms A,B,C0,C1 valid; contamination none. C1 invoked 0/153. SWE-CI 96 harness (`swe_ci` missing). v1 not interpreted. No second batch. Wave E / T08 not started. 0 paid calls. |
| 25 | 2026-08-18 | [052](coordinator-handoff-052.md) | Wave E (not started) | SWE-CI repair `1.4.0-h1-sweci-repair`. v3 96/96 digest `5db3c0f7…`; 0 harness; C1 invoked 0/24. v2 digest unchanged. Canonical H1 UNDECIDED/FAIL/FAIL. Operational B `local-deterministic` not hypothesis PASS. Wave E / T08 not started. 0 paid calls. |
| 26 | 2026-08-18 | [053](coordinator-handoff-053.md) | open `1.6.0-h3-longitudinal-scored` (do not execute) | Wave E **PASS**. Inherit `local-deterministic` into D/E/H operationally. Smoke `a49c992c…` 4/4 `scored=false`. 2070 not required. H3 unclaimed. `1.6.0` not created. val/test untouched. 0 paid calls. |
| 27 | 2026-08-18 | [054](coordinator-handoff-054.md) | do not Stage B; scored H3 remaps off 054 | Recursive-policy Stage A **INSUFFICIENT_SIGNAL**. `1.7.0` freeze digest `2850d7a4…`; `P+_yield_pos=0/43`; C0-shadow hermetic; H1 unchanged; `1.6.0` not created. 0 paid calls. |
