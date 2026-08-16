# Handoff — coordinator-handoff-047

## Meta

| Field | Value |
|---|---|
| Handoff ID | 047 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10-WAVE-B — close official H1 verifier bindings |
| Tip SHA (ACP) | no ACP source touched; docs-only seal at `f7d1a8481cab7025cbf405cd65a73bfdc2d3f5e6` (local, as with the Wave A seals) |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` @ `931153ba63e41da762e282cebb5d7b73f6f17d06` (local-only, no remote) |
| Experiment freeze | `v10-experiment-freeze-2026-08-16`, unchanged |
| Registry version | `1.0.0-t04-frozen` -> `1.1.0-official-bindings` (digest `3099cdba…`) |
| Deploy verify | **N/A** — maintenance-evals only; no ACP source changed |
| `stopped_reason` | `group_boundary_stop` (Wave B only; C and D not started by design) |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-047.md
wave: B
swe_ci_task_test_command_bound: yes
swe_ci_command_source: swe-ci-default@b2a0620f0168a5a89681be7919a98d9a49ab22af src/swe_ci/benchmark/tools.py::run_pytest (sha256 d1810aed…)
arb_trajectory_evaluator_bound: yes
arb_evaluator_path_version: arb-v2@07014c986f3deadb1548c62b32c0ffbe6a81465d `arb eval-trajectories` (agent-retrieval-bench 0.2.1) src/agent_retrieval_bench/trajectory.py::evaluate_trajectories (sha256 c5995d46…)
dev_smoke_swe_ci: pass
dev_smoke_arb: pass
adapter_versions: arb-adapter-1.1.0; swe-ci-adapter-1.1.0; registry 1.1.0-official-bindings
maintenance_evals_sha: 931153ba63e41da762e282cebb5d7b73f6f17d06
acp_changed: no
deploy_verify: N/A
scored_h1: no
blocker: none
stopped_reason: group_boundary_stop
```

## What the wave was for

T04 froze two verifier commands it could not yet write down, because the licensed
corpora were not on disk. Both were placeholders: `SWE_CI_TASK_TEST_COMMAND` and
`ARB_TRAJECTORY_EVALUATOR`. Until they resolved, "official pass" on those two
benchmarks was a name rather than a command, and no H1 result could mean
anything. Both are now bound, recorded, and executed non-scored on dev.

The machine-readable record is `manifests/benchmarks/verifier-bindings.yaml`
(`benchmark_verifier_bindings.v1`), loaded by `maintenance_evals.bindings`. The
narrative is `docs/VERIFIER_BINDINGS.md`.

## The bindings

**SWE_CI_TASK_TEST_COMMAND** resolves to upstream's own `run_pytest`:

```text
docker exec -w ${SWE_CI_REPO_DIR} -e PYTHONPATH=src:. ${SWE_CI_CONTAINER}
  python -m pytest tests --color=no --tb=short --disable-warnings -rfE
  --rootdir=${SWE_CI_REPO_DIR} --json-report --json-report-file=${SWE_CI_TEST_REPORT}
```

Source `src/swe_ci/benchmark/tools.py` lines 47-65 at
`b2a0620f0168a5a89681be7919a98d9a49ab22af`. This is the only test invocation
SWE-CI runs: once per task in `cold_test` and again after every evolution
iteration. All three placeholders are upstream parameters, not V10 inventions.
Official metrics come from `swe_ci.benchmark.summarize::metrics_func`.

**ARB_TRAJECTORY_EVALUATOR** resolves to `arb eval-trajectories`, console script
`arb` from distribution `agent-retrieval-bench` 0.2.1, implemented in
`src/agent_retrieval_bench/trajectory.py::evaluate_trajectories` at
`07014c986f3deadb1548c62b32c0ffbe6a81465d`. It is the upstream entry point that
scores an externally produced context acquisition.

Both source files were hashed at bind time and re-hashed during the smoke; both
matched. Both checkouts were confirmed at their pinned commits with clean
worktrees.

## Five harness mismatches, all corrected

Materializing the corpora exposed five places where the frozen command strings
could not have run. Each is recorded as a harness correction in the bindings
manifest with `semantics_changed: false`, and a test enforces that flag.

1. **SWE-CI**: the official command passed `--instance <id>`. `swe_ci.evaluate`
   has no such flag. The per-task official measurement is the bound `run_pytest`
   invocation; official metrics come from the upstream summarizer.
2. **SWE-CI**: the per-task test invocation sat in `v10_additional_commands`
   while `official_commands` held only the unexecutable driver. Swapped.
3. **SWE-CI**: the frozen prose names the official metric `ANC`. The summarizer
   emits `EvoScore(γ=1)`, `Resolved`, `Zero_reg.`, `ZRR`, and no key named ANC —
   confirming the naming defect T10 already recorded in
   `reports/LITERATURE_COMPARISON.md`.
4. **ARB**: the official command passed `--corpus`, `--candidate-filter`,
   `--no-keep-list` and `--sample`. The first three belong to the ranking
   baselines; `--sample` exists nowhere in the CLI. Rebuilt against the real
   `eval-trajectories` signature.
5. **ARB**: the frozen official metrics were snake_case renames (`mrr`,
   `recall_at_5/10/20`, `bcy_at_8k`, `selective_success_at_20`) of upstream's
   *ranking* family, which the bound evaluator does not emit.

Consequences, all versioned and none silent: `arb-adapter-1.0.1` -> `1.1.0`,
`swe-ci-adapter-1.0.1` -> `1.1.0`, registry `1.0.0-t04-frozen` ->
`1.1.0-official-bindings` with digest
`3099cdbfa397e027b6bc6065fb05e1679fab0e41b8d1e81951c103139433f24e`, and all five
experiment manifests resealed against it.

**Nothing about the benchmarks changed.** No split, no seed, no `frozen_groups`,
no task text, no hidden-artifact boundary, no upstream metric definition. A test
recomputes ARB and SWE-CI split assignments from the materialization evidence and
asserts they are byte-identical across the version bump.

## The ARB ranking family is deliberately unbound

ARB ships two official metric families. The bound one is the trajectory family
(retrieved / final / utilized file recall, precision, F1, plus `final_usage_drop`,
`utilization_drop`, `trajectory_redundancy`), emitted per evaluated sample. The
unbound one is the ranking family — `MRR`, `Recall@5/10/20`, `gold_coverage@8k`,
`selective_success@20` — which requires a corpus-wide ordering of candidate
files. No V10 arm produces one, and synthesizing an order from a trajectory would
invent something upstream never asked the agent for.

`OFFICIAL_RANKING_METRICS_UNBOUND` keeps that family under its true upstream key
names so the gap stays visible. **V10 ARB numbers are comparable to published
trajectory results and not to published ranking leaderboards**, and no V10 report
may present them as the latter.

A third set, `OFFICIAL_CONDITIONAL_METRICS` (`line_*@trajectory`,
`block_*@trajectory`, supporting-context recalls), appears only when the sample
carries the corresponding gold labels. A missing key there is an absent upstream
label, not a harness failure.

## DEV smoke — what was actually proved

Non-scored, dev split only, no hypothesis claimed. Driver
`scripts/smoke_verifier_bindings.py`, which refuses any task outside dev.
Evidence under `maintenance-evals/evidence/bindings/`.

**ARB — pass.** Two dev samples, one `code2test` (`vuejs/core`) and one
`comment2context` (`astral-sh/ruff`). Each was run twice through
`maintenance_evals.verification.run_verification` using the adapter's own frozen
command lists: a `superset-context` arm whose trajectory covers every path-like
value in the sample record, and an `empty-context` arm with a single absent path.
Official and additional commands exited zero in all four runs, every required
official metric key was present and numeric, and the evaluator discriminated on
both samples (`retrieved_file_recall` 1.0 versus 0.0).

The `empty-context` arm is a **negative control, not a baseline**. It exists so
that "the metric parsed" cannot be satisfied by an evaluator that silently scored
nothing. The same concern produced the one new V10-additional check in this wave,
`evalctl check-retrieval-record`, which fails unless the evaluator's per-sample
details actually carry numeric values for the named sample.

**SWE-CI — pass.** One dev task, `swe-ci/lepture__mistune__ff8312__28e7d4`,
prepared exactly as upstream `_init` prepares it and measured with upstream's own
`run_pytest`, `generate_nonpassed_dir` and `metrics_func`. Base commit 943 tests
passed, reference commit 957, observed gap 14 — matching the `test_gap` upstream
declares for that task in `metadata/default.csv`. The argv upstream actually
executed was **captured, not predicted** (`scripts/swe_ci_binding_probe.py`
records `subprocess.run` argv from inside `swe_ci.benchmark.tools`), and it
matches the recorded binding once the three placeholders are filled. Official
metrics at iteration zero parsed as `EvoScore(γ=1)` 0.0, `Resolved` 0.0,
`Zero_reg.` 1.0, `ZRR` 0.0 — the correct reading for a task nothing has worked on.

One deliberate deviation, recorded in the evidence as
`agent_layer_image_built: false`: the CLI-agent Docker layer was not built. It
installs Node and a coding-agent npm package, neither of which participates in
the test invocation being bound. A scored run that uses upstream's own agent
would need it.

## Also in this commit

- `maintenance_evals.verification._resolve_argv` now substitutes placeholders to
  a fixed point with a bounded pass count. The SWE-CI binding is itself a string
  containing placeholders, so a single pass left `${SWE_CI_REPO_DIR}` unresolved.
  Bounded so a self-referential value fails loudly instead of looping.
- `BenchmarkRegistry` gained an optional `verifier_bindings` path.
- Methodology pages, `BENCHMARK_LICENSES.md`, `THREAT_TO_VALIDITY.md` and
  `DEEPER_EVAL.md` B4 updated. `reports/V10_RESULTS.md` carries a dated
  "superseded in part" note; its frozen findings were **not** rewritten, because
  they read result sets that have not changed.

Pre-commit gates: maintenance-evals 199 tests passed, ruff clean on the committed
surface; ACP ruff clean and untouched.

## Findings the next coordinator must not rediscover

1. **CT102 CI ruff drift and the CT104 external model API key are both still
   open.** Nothing in this wave touched either. The CT104 key still means a
   "local-only" scored batch could silently fail over to a paid endpoint. Get a
   human decision before Wave C or D, exactly as handoff 046 said.
2. **A frozen command that has never been executed is not evidence.** Five of the
   command strings sealed at T04 were wrong in ways prose review could not
   detect — a flag that does not exist, four flags belonging to a different
   subcommand, two metric name sets that do not match upstream output. Any
   remaining unexecuted "official" command in this experiment deserves the same
   suspicion. SWE-Chain's was declared complete at T04 and was **not**
   re-verified in this wave.
3. **`maintenance-evals` has no Git remote.** SHAs are local-only.
4. **Untracked scratch scripts from the materialization session remain in
   `maintenance-evals/scripts/_*`.** They are not lint-clean and are not mine to
   delete; `ruff check .` reports errors on them while the committed surface is
   green. Check the committed file list, not the whole tree.

## Decisions the next coordinator must honor

1. **No hypothesis moved.** H1a, H1b, H1c remain unclaimed. An executable
   verifier is a precondition for a scored batch, not a substitute for one.
2. **Split assignments were not redrawn** across the adapter version bump, and a
   test now enforces it.
3. **ARB cannot answer ranking questions in V10.** Do not quote MRR or
   Recall@k, and do not compare V10 ARB output to a ranking leaderboard.
4. **SWE-CI's official metric is not "ANC".** Cite the four upstream summary
   keys. `EvoScore(γ=1)` is not the paper's EvoScore.
5. **The evidence under `evidence/bindings/` is non-scored** (`scored: false`,
   `hypotheses_claimed: []`) and must never be promoted into a result set.

## Next coordinator: first actions

1. Read this handoff and `docs/VERIFIER_BINDINGS.md`; do not re-derive the
   bindings.
2. Resolve the CT104 model-key question with a human before proposing any scored
   batch.
3. If a scored H1 is authorized, ARB is the cheaper of the two: the evaluator is
   fast and needs no Docker. SWE-CI needs the per-task environment images and, if
   upstream's own agent is used, the CLI-agent layer that this wave skipped.

## Open risks

- The ARB ranking family stays unbound; H1 conclusions about retrieval are
  conclusions about acquired context, not about ranking quality.
- SWE-CI dev smoke covered one task on one image. Image availability across the
  remaining 99 default-split tasks is untested.
- CT102 pipeline still red; any future tip looks unverified from Actions alone.
