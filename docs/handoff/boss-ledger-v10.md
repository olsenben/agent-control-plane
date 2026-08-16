# Boss ledger — V10 Maintenance Evaluation & Economic Bake-off

Epic supervisor state. Prior: [boss-ledger-v9.md](boss-ledger-v9.md) (complete). Epic: [boss-ledger-v10-maintenance-evaluation-revised.md](../boss-ledger-v10-maintenance-evaluation-revised.md). Plan: `.cursor/plans/v10_eval_bakeoff_30f4388b.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | V10 — Maintenance Evaluation & Economic Bake-off |
| **Baseline tip** | `4376ef4` live-certified; docs/tag SHA `2532de7` (`eval-baseline-2026-08`) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) + V10 plan dual-freeze discipline |
| **Integration branch** | `main` |
| **Epic status** | **running** — Waves A and B sealed; both official H1 verifiers are executable; no scored H1 yet |
| **Tickets done** | 10 / 12 (T08 and T09 remain WaitingHuman); **0 / 5 hypotheses decided** |
| **Next ticket** | Wave C — live C1 observation against the real 2070 endpoint (blocked on the CT104 model-key decision) |
| **Latest handoff** | [047](coordinator-handoff-047.md) |
| **Last boss action** | 2026-08-16 — Wave B PASS; both bindings bound and DEV-smoked non-scored; Wave C not started |

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
H1a unclaimed  - corpora materialized, official verifiers now executable; scored batch not yet run
H1b unclaimed  - corpora materialized, official verifiers now executable; scored batch not yet run
H1c unclaimed  - WaitingHuman + no live C1 run against the real 2070 endpoint exists
H2  unclaimed  - WaitingHuman FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE + credentials + spend cap
H3  instrument verified (T07); agent dispatch path cleared under `1.2.0-eval-dispatch`; outcome still unclaimed until scored thresholds
```

No pre-registered threshold was evaluated and no primary test was run. The
provisional `local-recursive-fallback` selection is `PROVISIONAL_NOT_FOR_H2` and
is not an H1 answer.

## Open human gates before any scored batch

```text
1. MATERIALIZE_LICENSED_CORPORA — CLEARED 2026-08-16
   (ARB 427 / SWE-CI 100 / SWE-Chain 155; evidence under
   maintenance-evals/evidence/materialization/; raw corpora outside Git)
2. EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS — CLEARED 2026-08-16
   (generic ACP maintenance_eval_dispatch.v1; experiment_version 1.2.0-eval-dispatch;
    T07 instrument preserved; H3 claim still requires scored agent batch)
3. FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE + credentials + spend cap -> unlocks H2
4. Live C1 observation against the real 2070 endpoint -> required before any C1 batch is scored
5. Decide H1 on dev, re-freeze the strategy D/E/H inherit -> re-run inheriting arms if the winner differs
6. CT104 external model API key — decide (revoke, or explicitly freeze and accept)
   before any "local-only" scored batch; carried from Wave A, still open
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
