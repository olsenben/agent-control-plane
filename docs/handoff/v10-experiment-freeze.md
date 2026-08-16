# V10 EXPERIMENT FREEZE

| Field | Value |
|---|---|
| Freeze ID | `v10-experiment-freeze-2026-08-16` |
| Sealed (UTC) | 2026-08-16 |
| Sealed by | V10 T04 |
| Git tag | `v10-experiment-freeze-2026-08-16` in `ai-sdlc-lab/maintenance-evals`, annotated, at commit `b282f6d` |
| ACP tag | **Not required.** T04 changed no `agent-control-plane` runtime code, model routing, policy, or worker image. The platform freeze remains `eval-baseline-2026-08` at `2532de7cf5098baa461e49b92e0d338c089cff45`. |
| Benchmark registry version | `1.0.0-t04-frozen` |
| Benchmark registry SHA-256 | `bcb05e1db2b8974d0a45198a58476d7c7e041be55d5a4fbdc0cba22202713913` |

## The gate

**No scored run may execute against a benchmark whose registry entry says
`scored_runs_allowed: false`.** At seal time exactly one benchmark is scorable:
the custom longitudinal corpus, which is authored in `maintenance-evals`,
carries no upstream licence, and is materialized. Everything else is frozen at
the contract level and blocked on human approval.

This is enforced in three places, not just asserted here: the registry, each
split policy, and each experiment manifest, with a test
(`test_only_the_synthetic_corpus_may_be_scored_at_freeze`) that fails if they
disagree.

Changing any value in this document invalidates the freeze and requires a new
experiment version. Harness fixes invalidate affected runs; they never rewrite
results.

## 1. Benchmark versions

Every upstream commit below was verified against the GitHub API on 2026-08-16.

| Benchmark | Frozen version | Upstream commit | Commit date |
|---|---|---|---|
| Agent-Retrieval-Bench | `arb-v2@07014c98…` | `07014c986f3deadb1548c62b32c0ffbe6a81465d` | 2026-08-04 |
| SWE-CI | `swe-ci-default@b2a0620f…` | `b2a0620f0168a5a89681be7919a98d9a49ab22af` | 2026-06-10 |
| SWE-Chain | `swe-chain-v1@4d485122…` | `4d4851222f6d64b48a9917af48dd5fd4d9df4a0d` | 2026-05-07 |
| SWE-bench Verified (optional) | `swe-bench-verified@128cbd1a…` | `128cbd1a5759694874e6bd56624cb2fd6fb079e2` | 2026-08-15 |
| custom-longitudinal | `synthlab-longitudinal-1.0.0` | authored in repository | 2026-08-16 |

Source of truth: `maintenance-evals/manifests/benchmarks/registry.yaml`.
Methodology, licence, metric, statefulness, hidden-test boundary, and deviations
for each: `maintenance-evals/docs/benchmarks/*.md`.

## 2. Adapters

| Benchmark | Module | Adapter version | Field map status |
|---|---|---|---|
| Agent-Retrieval-Bench | `maintenance_evals.adapters.agent_retrieval_bench` | `arb-adapter-1.0.0` | declared, pending materialization |
| SWE-CI | `maintenance_evals.adapters.swe_ci` | `swe-ci-adapter-1.0.0` | declared, pending materialization |
| SWE-Chain | `maintenance_evals.adapters.swe_chain` | `swe-chain-adapter-1.0.0` | declared, pending materialization |
| SWE-bench (optional) | `maintenance_evals.adapters.swe_bench` | `swe-bench-adapter-1.0.0` | declared, pending materialization |
| custom-longitudinal | `maintenance_evals.adapters.longitudinal` | `longitudinal-adapter-1.0.0` | observed |

Every adapter reads physical field names only through its frozen field map under
`manifests/benchmarks/field-maps/`, and fails closed on a missing declared
field. A field map that turns out to disagree with real data is a harness
correction: it bumps the adapter version and is recorded in the benchmark's
methodology page. It is never a silent default.

Each adapter refuses to emit a task whose agent-visible text contains a
verifier-only value, comparing values rather than field names.

## 3. Task identifiers

| Benchmark | Task ID form | Frozen how |
|---|---|---|
| Agent-Retrieval-Bench | `arb/<subset>/<sample_id>` | Enumerated at materialization within frozen repositories |
| SWE-CI | `swe-ci/<instance_id>` | Enumerated at materialization under the frozen hash assignment |
| SWE-Chain | `swe-chain/<chain_id>/<step:03d>` | Enumerated at materialization within frozen chains |
| SWE-bench (optional) | `swe-bench-verified/<instance_id>` | 20 lowest-ranked instances under the frozen selection hash |
| custom-longitudinal | `longitudinal/<repository>-e<NN>` | **Fully enumerated now**: 30 files in `manifests/tasks/longitudinal/` |

## 4. Splits

Full detail: `maintenance-evals/docs/BENCHMARK_SPLITS.md`. Seed `20260815` for
every policy.

| Benchmark | Unit | Method | dev / validation / test |
|---|---|---|---|
| Agent-Retrieval-Bench | repository | greedy_balanced | 43 / 192 / 192 samples over 6 / 9 / 10 repositories |
| SWE-CI | instance | hash_bucket | ≈10 / 45 / 45 of 100, enumerated at materialization |
| SWE-Chain | package | greedy_balanced | 2 / 5 / 5 chains over 2 / 4 / 3 packages |
| SWE-bench (optional) | instance | hash_bucket, capped at 20 | 20 / 0 / 0, dev-only, never scored |
| custom-longitudinal | repository | greedy_balanced | 6 / 12 / 12 episodes over 1 / 2 / 2 repositories |

Rules that hold for the life of the experiment version:

- A split may not be redrawn, resized, or re-seeded.
- A `test` split may not be inspected before T09.
- SWE-CI's one-shot leakage repair (collapse a repository spanning splits onto
  its majority split, ties in dev/validation/test order) is applied exactly once
  at materialization, before any outcome is observed. It is the only permitted
  adjustment anywhere in this freeze.
- SWE-Chain is never split inside a chain; the longitudinal corpus is never
  split inside a repository.

## 5. Verification commands and the dual metric

Every task carries two frozen command lists:

- `official_commands` — the upstream verifier, reproduced as upstream defines
  it. This produces `official_benchmark_pass`.
- `v10_additional_commands` — the frozen V10 checks. These produce
  `v10_additional_verification_pass`.

The two are reported separately and neither may overwrite the other.
`verified_success` requires both. An arm that raises the official signal while
lowering the additional signal has not improved maintenance quality, and the
statistical plan requires reporting it that way. This is the UTBoost lesson
applied as a rule rather than a caveat.

`hidden_artifacts_excluded_from_context: true` on every task. For the
longitudinal corpus the boundary is enforced by git: each episode's published
snapshot has exactly one ref, its starting commit, so the reference resolution
is unreachable from a clone. The build verifier asserts this for all 30
episodes.

Two command bindings remain unresolved until materialization and are tagged
`materialization_binding_required` on the affected tasks:
`ARB_TRAJECTORY_EVALUATOR` and `SWE_CI_TASK_TEST_COMMAND`.

## 6. Arms

Nine arms, frozen in the manifest schema enum:

| Arm | Context strategy | Memory | Controller backend | Frontier |
|---|---|---|---|---|
| `local-direct` | ordinary bounded repository/tool context | off | none | no |
| `local-deterministic` | deterministic CT103 preflight, graph, FTS, context pack | off | none | no |
| `local-recursive-fallback` | deterministic preflight + conditional recursion | reset | deterministic (C0) | no |
| `local-recursive-2070` | deterministic preflight + conditional recursion | reset | model (C1) | no |
| `local-recursive-memory-reset` | best local recursive strategy frozen from H1 | reset | frozen_best | no |
| `local-recursive-memory` | best local recursive strategy frozen from H1 | preserve_verified | frozen_best | no |
| `frontier-direct` | provider-native exploration where feasible | suite_rule | none | no |
| `frontier-same-harness` | frozen CT103 context, ACI sandbox, verification | suite_rule | frozen_best | no |
| `hybrid` | deterministic → conditional recursion → typed escalation | suite_rule | frozen_best | yes |

`local-recursive-memory-reset` and `local-recursive-memory` inherit the H1
winner. That inheritance is itself a freeze commitment: the winner is selected
on the **dev** split only, is frozen before H3 runs, and may not be revisited
after H3 outcomes are visible.

## 7. Prompts, model configuration, and recursive trigger logic

These are platform properties, frozen by T00/T00.5 and cited here rather than
restated. Authority: `docs/evals/V10_BASELINE.md`.

| Item | Frozen value |
|---|---|
| Platform baseline tag | `eval-baseline-2026-08` at `2532de7cf5098baa461e49b92e0d338c089cff45` |
| Patch-author model | `qwen2.5-coder:14b`, quantization `Q4_K_M` |
| Controller model | `qwen2.5-coder:3b` (`MODEL_2070_NAME`) |
| Model routing policy | `official` |
| LiteLLM config SHA-256 | `e39938abf73805ca141252d8c663b65b4b545e93533f562aedd81f8534614fd7` |
| Recursive-context config SHA-256 | `8258dc951f65aa04b8331293574ce3533fabf33a1798926c49468fad94ecc9c5` (T00.5 amended) |
| CI-grounded recursive loop config SHA-256 | `b59afc88c38e7a37acd1a47ec2af69bc1c1589e420f12893c561690095c9b7dd` |
| Command registry hash | `9fe074e04811d9eab61f61320be2a1a857dabf5892a2f2ae66a3366224ed75a5` |
| Tool policy hash (`tool_policy.v2`) | `fe698437e6ab94e7d26e9fde5bfc44bf7c88c57d12d7df347f1d251fe9a6e996` |
| Adequacy profiles SHA-256 | `5bf4c69fadc70419c08fd531028ed06d8e6f7e009972406b3ca889c6b8f37d49` |

**Recursive trigger logic.** Invocation is conditional, not always-on.
Budgets: maximum depth 2, maximum subcalls 6, maximum graph queries 20, maximum
memory records 24, maximum wall time 180 s, maximum prompt tokens per subcall
8,192, maximum total input/output tokens 60,000/12,000, output maximum 16,000
characters, repository write / network / secret paths all false. The
CI-grounded loop is bounded by `max_plan_iterations=2`,
`max_patch_iterations=3`, `max_ci_repair_iterations=3`,
`max_selected_evidence_refs=24`, `max_selected_chars=12000`.

**C0 versus C1 is a telemetry claim, not a label.** `controller_backend`
records the configured arm; only `controller_model_invoked=true` with a resolved
`controller_model_id` proves a live controller call happened. Deterministic
fallback may never be reported as the live 2070 controller.

**Prompts.** Task text comes from the benchmark, not from V10. Three of the five
benchmarks supply agent-facing text directly (ARB query, SWE-Chain
specification, SWE-bench issue). SWE-CI ships none, so the adapter supplies one
frozen maintenance directive, recorded verbatim in
`maintenance_evals.adapters.swe_ci.MAINTENANCE_DIRECTIVE`; changing that string
changes the task. Harness system prompts are platform-frozen at the baseline SHA
above.

## 8. Budgets

| Manifest | Wall/task | Solver attempts | Repair attempts | Paid USD/task |
|---|---|---|---|---|
| `v10-context-ablation` | 3600 s | 3 | 3 | 0.00 |
| `v10-maintenance-end-to-end` | 3600 s | 3 | 3 | 0.00 |
| `v10-longitudinal` | 3600 s | 3 | 3 | 0.00 |
| `v10-frontier-hybrid` | 3600 s | 3 | 3 | 100.00 |

Per-task adapter limits: ARB 1800 s / 1 attempt (retrieval is single-shot);
SWE-bench sanity 1800 s / 3; longitudinal 1800 s / 3; SWE-CI and SWE-Chain
3600 s / 3.

The one-hour SWE-CI envelope is materially tighter than upstream's reported
48 hours on 32 cores at 16-way concurrency, and must be stated in any comparison
against published numbers.

## 9. Sampling, ordering, repeats, and cache policy

| Item | Frozen value |
|---|---|
| `execution_order.strategy` | `seeded_block_randomized` |
| `execution_order.seed` | **`20260815`** in all four manifests |
| Split assignment seed | `20260815` in all five policies |
| Sampling | `temperature: 0.0`, `top_p: 1.0`, `seed: 20260815` |
| Repeats per task | 3 |
| Stochastic-arm minimum | 3 |
| Infrastructure failure consumes a repeat | No |
| `cache_policy.mode` | `isolated_per_run` (all four manifests) |
| `cache_policy.clear_between_tasks` | `true`, except `v10-longitudinal` where it is `false` because carried state is the independent variable |
| `cache_policy.reuse_between_arms` | `false` everywhere, without exception |

The per-manifest placeholder seeds 1001–1004 were superseded by `20260815` at
this freeze. Block structures differ per manifest, so a shared seed does not
align orderings across experiments.

## 10. Failure classification

Exactly one of `harness`, `infrastructure`, `evaluated_agent` per unsuccessful
attempt.

- `infrastructure` — excluded and rerun in the same randomized slot; does not
  consume a repeat.
- `harness` — invalidates affected runs. Audit records are retained; results are
  never rewritten. If evaluated behaviour changed, a new experiment version
  starts.
- `evaluated_agent` — a real failure, scored as a failure.

Invalid runs retain an audit record and are excluded from scoring.

## 11. Statistical plan

Frozen in `maintenance-evals/docs/STATISTICAL_PLAN.md`. Summary of the binding
commitments:

- Independent unit is the repository (ARB, SWE-CI, longitudinal) or the chain
  (SWE-Chain), never the run. Repeats collapse to a per-task mean.
- Primary inference is a stratified randomization (permutation) test on paired
  per-task outcomes, valid because arm ordering is randomized by the harness.
- Family-wise error controlled by Holm-Bonferroni at α = 0.05 across the five
  primary tests. Secondary endpoints are exploratory and may not be promoted.
- Cluster bootstrap intervals are **not** reported where clusters number fewer
  than five, which is known in advance for the longitudinal validation split
  (2 repositories) and the SWE-Chain validation split (4 chains).
- The study is not powered for the 5-percentage-point equivalence margins in
  H2. A non-significant H2 result is reported as underpowered, never as
  equivalence.
- Negative and neutral findings are reported with equal prominence.

## 12. Price table version

`maintenance-evals/pricing/pricing-2026-08.yaml`, version `2026-08`, effective
from 2026-08-01, status `pre_experiment_freeze`, **containing no price rows**.

This is deliberate. No frontier provider or model has been selected, so there is
no rate to cite, and an absent row makes any paid-cost claim explicitly unknown
rather than quietly wrong. Cost status is one of `calculated`,
`no_paid_api_usage`, `unknown_usage`, `unknown_price`; unknown usage or price
always yields a null dollar claim.

A price table referenced by a result may never be rewritten. Adding the frontier
row creates a new pricing version.

## 13. Dual metrics

Recorded per run and never merged into a single headline number:

| Metric | Meaning |
|---|---|
| `official_benchmark_pass` | The upstream verifier's own verdict |
| `v10_additional_verification_pass` | The frozen V10 additional checks |
| `verified_success` | Both of the above |
| `negative_transfer` | Official passes, additional fails |
| `verifier_adequacy_notes` | Recorded limitations and disagreements |

Benchmark-native metrics are preserved rather than collapsed: ARB reports `mrr`,
`recall_at_{5,10,20}`, `bcy_at_8k`, and `selective_success_at_20`; SWE-CI
reports ANC over iterations; SWE-Chain reports all six per-transition verdict
categories, not a bare resolving rate.

## 14. Open gates

Both gates below are machine-readable in the manifests
(`resolve_before_scoring`) and block the runs they name.

### `MATERIALIZE_LICENSED_CORPORA` — WaitingHuman

No upstream corpus has been downloaded into `maintenance-evals`, and none is
redistributed from it. Blocks: `v10-context-ablation`,
`v10-maintenance-end-to-end`, `v10-frontier-hybrid`, and the SWE-Chain half of
`v10-longitudinal`.

To clear, per benchmark: recorded human approval to fetch; recorded
materialization evidence enumerating the resulting task identifiers; a registry
edit setting `scored_runs_allowed: true`; an amendment entry in this document.
Clearing this gate does **not** permit re-running any split assignment, and
doing so would be a protocol violation. Details and per-benchmark conditions:
`maintenance-evals/docs/BENCHMARK_LICENSES.md`.

### `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` — WaitingHuman

No frontier provider, model, or price has been committed. `frontier_id` is
`null` in all four manifests. Blocks `v10-frontier-hybrid` entirely, and with it
H2.

To clear: a human selects the provider and model, a cited price row is added
under a new pricing version, `frontier_id` is set in `v10-frontier-hybrid`, and
an amendment entry is added here. T04 declined to invent this because a
cost-per-verified-success claim built on an uncited rate is worse than a stated
gap.

### Not a gate

`v10-longitudinal` on the custom corpus is clear to execute. This is the
synthetic-only scored path: if no external corpus is ever approved, V10 can
still run a hypothesis-bearing experiment (H3, memory-reset versus
verified-memory) with the reduced scope stated in the report.

## 15. Amendment log

| Date | Change | Effect |
|---|---|---|
| 2026-08-16 | Freeze sealed | — |

Every future entry must state what changed, why, and whether it starts a new
experiment version.
