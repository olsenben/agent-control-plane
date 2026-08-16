# Handoff — coordinator-handoff-039

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 039 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T04 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Evaluation repo tip | `b282f6d` (tagged `v10-experiment-freeze-2026-08-16`) |
| ACP repo | Documentation only; no commit made, tree left for the coordinator |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `ticket_done` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-039.md
ticket: T04
status: Done (WaitingHuman on corpus licences and frontier pricing)
repo: ai-sdlc-lab/maintenance-evals
tip: b282f6d
tag: v10-experiment-freeze-2026-08-16
freeze_doc: agent-control-plane/docs/handoff/v10-experiment-freeze.md
tests: 120 passed
ruff: All checks passed!
corpus_verify: 30/30 episodes discriminate; 4/4 traps confirmed
deploy_verify: N/A (no agent-control-plane runtime change)
blocker: MATERIALIZE_LICENSED_CORPORA; FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE
next_ticket_id: T05 (longitudinal H3 path only until the licence gate clears)
stopped_reason: ticket_done
```

## Slice outcome

The T04 experiment freeze is sealed. The seal itself is
[`v10-experiment-freeze.md`](v10-experiment-freeze.md); everything below is what
went into it.

### Benchmark layer

- **Registry** (`manifests/benchmarks/registry.yaml`) is the single source of
  truth for upstream identity. Four upstream commits were verified against the
  GitHub API on 2026-08-16 rather than transcribed: ARB
  `07014c98…` (2026-08-04), SWE-CI `b2a0620f…` (2026-06-10), SWE-Chain
  `4d485122…` (2026-05-07), SWE-bench `128cbd1a…` (2026-08-15).
- **Methodology pages** under `docs/benchmarks/` record, per benchmark: upstream
  source and commit, paper URL and DOI, licence, official metric, unit of
  evaluation, statefulness, hidden-test boundary, what the agent may see, what
  the verifier may see, required transformations, and deviations from official
  evaluation.
- **ARB keeps its own metrics.** `mrr`, `recall_at_{5,10,20}`, `bcy_at_8k`, and
  `selective_success_at_20` are preserved per sample. The adapter will not
  collapse a retrieval sample into a verified-patch outcome, because that
  substitutes a different question for the benchmark's own.
- **SWE-Chain keeps all six verdict categories** rather than a resolving rate,
  because regression matters as much as resolution in a maintenance chain.
- **SWE-bench is documented as optional** and dev-only, tagged `sanity_only` and
  `not_scored`. It exists to distinguish a harness defect from a
  benchmark-specific integration problem, and may not support a claim.

### Adapters

Five narrow adapters to `maintenance_eval_task.v1`. Each reads physical field
names only through a frozen field map, so an upstream rename becomes a loud
harness failure instead of a silent behaviour change, and each refuses to emit a
task whose agent-visible text contains a verifier-only **value** — the guard
compares values, not field names, because the leak that matters is a gold path
reaching the prompt.

Two adapters refuse rather than guess: SWE-Chain will not invent a package's
source URL, and no adapter will accept a short commit SHA.

### Splits

Frozen in `docs/BENCHMARK_SPLITS.md`, seed `20260815` throughout, with two
mechanisms and the difference recorded rather than hidden:

- **Enumerated** where membership was knowable: ARB by repository (43/192/192
  samples), SWE-Chain by package (2/5/5 chains), longitudinal by repository
  (6/12/12 episodes).
- **Frozen assignment function** where the corpus could not be downloaded:
  SWE-CI and the SWE-bench subset use a keyed hash, so materializing later
  reproduces exactly this membership and cannot re-draw it.

Unit choices are deliberate. ARB splits by repository because the corpus is
imbalanced (Gin holds 88 of 427 samples) and a sample-level draw would put one
repository on both sides of the held-out boundary. SWE-Chain splits by package,
not chain, because chains of one package share a Dockerfile and a test layout.
The longitudinal split treats `ledger-core` and `ledger-api` as one coupling
group because the latter vendors the former's contract.

### Longitudinal corpus

5 repositories, 6 ordered episodes each, 30 episodes, 9 memory roles. Synthetic
and authored here; no employer or private data.

The corpus is not just built, it is **proved to discriminate**.
`scripts/build_longitudinal_corpus.py --verify` requires, for all 30 episodes,
that the visible test fails at the starting commit, passes at the reference
resolution, that the whole suite still passes there, and that the verifier-only
check passes. All 30 pass.

Each of the 4 harmful-memory traps additionally ships `trap_blocks`: the
plausible-but-wrong module a misapplied memory would produce. The verifier
executes it and requires that it **passes the visible test and fails the
additional check**. A trap that fails the visible test is not a trap and is
rejected at build time. This caught two real defects during T04: two episodes
labelled traps had visible tests a no-op would pass.

Backward leakage is prevented by git, not by convention: each episode is
published as a bare snapshot whose single ref is its starting commit, so the
reference resolution is unreachable from the clone. The verifier asserts this.

### Manifests

All four are now `status: frozen`, carry an `experiment_freeze` block naming the
registry hash, and use execution seed `20260815`. Frozen versions, splits, and
task selections replace every `RESOLVE_IN_T04` placeholder.

`v10-longitudinal` is `scored_runs_allowed: true` — the only runnable manifest.
Its SWE-Chain half stays gated and must be reported as deferred, not absent.

### Statistical plan

`docs/STATISTICAL_PLAN.md`, frozen before any run. Independent unit is the
repository or chain, never the run; repeats collapse to a per-task mean; primary
inference is a stratified randomization test (valid because the harness
randomizes arm order); Holm-Bonferroni across the five primary tests.

It states two uncomfortable things in advance, on purpose: cluster bootstrap
intervals will **not** be reported for the longitudinal validation split (2
clusters) or the SWE-Chain validation split (4 clusters), and the study is not
powered for H2's 5-point equivalence margins, so a null H2 will be reported as
underpowered rather than as equivalence.

## Decisions the next coordinator must honor

1. **No scored run against a benchmark whose registry entry says
   `scored_runs_allowed: false`.** Enforced in the registry, the split policies,
   and the manifests, with a test that fails if they disagree.
2. **No split may be redrawn, resized, or re-seeded**, including after the
   licence gate clears. SWE-CI's one-shot leakage repair is the only permitted
   adjustment anywhere in this freeze, and it runs once at materialization
   before any outcome is observed.
3. **No `test` split may be inspected before T09.**
4. Clearing `MATERIALIZE_LICENSED_CORPORA` requires, per benchmark: recorded
   human approval, recorded materialization evidence enumerating task
   identifiers, a registry edit, and an amendment entry in the freeze document.
5. Clearing `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` requires a provider and
   model decision plus a cited price row under a **new** pricing version. A
   price table referenced by a result may never be rewritten.
6. The H1 winner that `local-recursive-memory*` inherits is selected on **dev
   only** and frozen before H3 runs.
7. SWE-Chain `chained` and `independent_step` regimes may never be pooled.
8. `official_benchmark_pass` and `v10_additional_verification_pass` are reported
   separately. Neither may overwrite the other.

## Changes a reviewer should look at deliberately

Three judgement calls that a coordinator may want to revisit:

1. **H2 was removed from `v10-maintenance-end-to-end`.** Every arm in that
   manifest is local, so it had no frontier baseline and could not test H2. H2
   is tested by `v10-frontier-hybrid`, which declares the frontier arms. The
   hypothesis set is still complete across the four manifests. Revert this if
   the intent was a cross-manifest comparison, but then the pairing needs to be
   written down.
2. **`execution_order.seed` changed from 1001–1004 to `20260815`** in all four
   manifests, to match the freeze instruction and the split seed. Block
   structures differ per manifest, so a shared seed does not align orderings.
3. **`config-loader-e06` was rewritten** from a verified-repair episode into a
   harmful-memory trap, because the held-out split otherwise contained no trap
   and negative transfer would have been measurable only where the harness was
   tuned.

## Verification performed

- `python -m pytest tests/ -q` — 120 passed, up from 16 at T03: 102 in the new
  `tests/test_benchmark_freeze.py` (many parametrized over the five benchmarks
  and the 30 frozen task records) plus 2 added to `tests/test_contracts.py`.
- `python -m ruff check .` — All checks passed.
- `python scripts/build_longitudinal_corpus.py --verify` — 30/30 episodes
  discriminate; 4/4 traps confirmed; no snapshot reaches its own resolution.
- `python scripts/build_longitudinal_corpus.py --check-lock` — rebuild is
  byte-identical, so `corpus.lock.json` is reproducible.
- `python scripts/materialize_longitudinal_tasks.py --check` — 30 frozen task
  files current.
- Four upstream commits confirmed present via the GitHub API, with commit dates
  matching the registry.

Tests cover: registry/field-map/split-policy/adapter version agreement, the
scored-run gate, reproducibility of every enumerated split assignment,
hash-bucket stability under partial materialization, the SWE-CI repair rule,
capped order-independent subset selection, per-adapter intent preservation,
leakage refusal, and the 30 frozen longitudinal task records.

## Deployment

Deploy verification is **N/A**. T04 changed only the evaluation repository and
`agent-control-plane` documentation. No ACP runtime code, model routing, policy,
worker image, credential, CT103 behaviour, or CT104 behaviour changed. The
platform freeze remains `eval-baseline-2026-08` at
`2532de7cf5098baa461e49b92e0d338c089cff45`.

No ACP git tag is needed for the same reason; the experiment tag lives in
`maintenance-evals`.

## Open follow-ups

- **WaitingHuman:** approve acquisition and redistribution terms for ARB,
  SWE-CI, SWE-Chain, and optionally SWE-bench Verified. ARB is the strictest:
  its samples inherit the licence of each of 25 source repositories rather than
  carrying a single grant.
- **WaitingHuman:** select the frontier provider and model and add a cited price
  row under a new pricing version, or record the decision to drop H2.
- The coordinator should commit the ACP documentation tree (this handoff, the
  freeze document, `docs/benchmarks/README.md`, and the ledger edits); it was
  left uncommitted because the ACP working tree contains unrelated V9 changes.
- T05 may proceed on `v10-longitudinal` (H3) now. It may not touch
  `v10-context-ablation`, `v10-maintenance-end-to-end`, or
  `v10-frontier-hybrid`.
