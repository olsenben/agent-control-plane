# Boss Ledger — V10 Maintenance Evaluation & Economic Bake-off

**Status:** Proposed epic — ready for Cursor planning  
**Date:** 2026-08-15  
**Primary repo:** `ai-sdlc-lab/agent-control-plane`  
**Companion repo:** `ai-sdlc-lab/maintenance-evals` (new, evaluation-only; create during T01)  
**Prior completed epics:** V4/V4.1/V4.1.1/V4.1.2, V5 governance, V9 Agent Observatory  
**Primary deferred research item absorbed here:** V4 T12 — controller/memory bake-off + longitudinal evaluation + negative-transfer metrics
**Public benchmark strategy:** SWE-CI (primary end-to-end maintenance), SWE-Chain (dependency/evolution), Agent Retrieval Bench (context selection), custom longitudinal sequences (memory/moat), optional SWE-bench-family sanity subset  
**Orchestration:** use `docs/epic-orchestration.md`  
**Execution rule:** one implementation ticket per wave unless a ticket explicitly says otherwise. `DEPLOY_VERIFY_TEMPLATE` must pass after every control-plane change before the next dependent ticket begins.

---

## 0. Executive decision

The platform feature spine is sufficiently complete for the next phase.

Do **not** start another autonomy, Jira, scanner, security-review, CI-minimizer, UI, multi-agent, RL, or productization epic before this evaluation finishes.

V10 exists to answer three falsifiable questions:

1. **Context lift:** Does deterministic + recursive context improve the verified maintenance performance of the same local coding model?
2. **Economic substitution:** Can local/RLM-first execution with selective frontier escalation achieve near-frontier verified quality at materially lower paid inference cost?
3. **Longitudinal lift:** Does verified repository history make later maintenance tasks cheaper or more reliable without unacceptable negative transfer?

V10 must answer those questions on **known public benchmarks as well as controlled custom sequences**.

The public benchmark stack is:

```text
Agent Retrieval Bench  -> component-level context/retrieval quality
SWE-CI                 -> primary end-to-end maintenance/evolution benchmark
SWE-Chain              -> dependency upgrade / chained maintenance benchmark
SWE-bench-family       -> optional secondary sanity/comparability subset
custom longitudinal    -> memory compounding / negative-transfer benchmark
```

No single benchmark is treated as sufficient evidence for the full product thesis.

The product/research thesis survives only if at least one material effect is reproducible on held-out or external tasks, not merely on home-authored fixtures.

# 1. Non-goals

V10 must **not**:

- optimize headline SWE-bench score for its own sake;
- add new agent personas or an agent swarm;
- make the recursive worker mandatory;
- train or fine-tune models;
- add RL;
- add a new dashboard when Agent Observatory already exists;
- add Jira, Linear, GitHub, GitLab, Snyk, Wiz, Semgrep, Sonar, or other product integrations unrelated to benchmark ingestion;
- add `/agent security-review`;
- add graph-gated fix approval or CI minimization;
- expand write authority;
- relax SRT / sandbox / CT103 brokerage / CT102 verification boundaries;
- use employer/private repositories, prompts, schemas, tickets, logs, findings, or policies as benchmark fixtures;
- change prompts, routing rules, context strategy, model weights, or verifier profiles after the pre-registered experiment begins unless the run is invalidated and restarted as a new experiment version.

Bug fixes to the **evaluation harness** are allowed. Behavioral fixes to the **agent under evaluation** require a new frozen baseline/version.

---

# 2. Existing invariants V10 preserves

The following remain true:

```text
CT103 = policy, credential, state, routing, and Gitea mutation authority.
CT104 = bounded untrusted execution; no canonical-state ownership.
CT102 = independent CI verification for checks actually run.
Model hosts = inference only; no repository execution.
Agents are stateless.
Agents emit events.
Reducer owns canonical state.
Target repos are thin clients.
Recursive context is optional and conditional.
Verification claims are scoped to machine-recorded evidence.
No model narrative can mark work verified.
```

V10 must use the existing:

- typed AgentSession lifecycle;
- exact-SHA state and policy provenance;
- deterministic preflight;
- graph/context pack;
- reusable memory admission rules;
- conditional `recursive_context_result.v1`;
- sandboxed repair;
- closed-world diff gate;
- CT103 publication brokerage;
- CT102 CI truth loop;
- scoped verification claims;
- reward/trajectory logging;
- Agent Observatory/replay.

---

# 3. Baseline inconsistency that must be resolved first

The current documentation contains stale text describing CT104 Gitea write tokens as demo debt even though the later milestone/status section records:

```text
CT104 Gitea write tokens retired.
CT103 independent patch validation + push brokerage done.
V4.1.1 trust-boundary hardening done.
```

V10 must verify **deployed reality**, then update stale documentation before freezing the experiment.

The evaluation baseline is invalid if the documented trust boundary and the deployed trust boundary disagree.

---

# 4. Research hypotheses

## H1 — context architecture lift

For the **same Qwen Coder 14B patch-author model**, structured context should improve either:

- repository/context retrieval quality;
- verified end-to-end success;
- cost/latency at approximately equivalent verified success.

H1 is decomposed into three comparisons:

```text
A -> B   value of deterministic CT103 preflight / graph / bounded evidence
B -> C0  value of recursive orchestration with deterministic fallback
C0 -> C1 incremental value of a live model-backed 2070 recursive controller
```

Primary component benchmark:

```text
Agent Retrieval Bench
```

Primary downstream maintenance check:

```text
held-out SWE-CI subset
```

No frontier model is required to decide H1.

---

## H2 — economic substitution

A local/RLM-first hybrid should preserve most frontier-agent verified performance while materially reducing paid frontier inference.

Primary external comparisons:

```text
SWE-CI
SWE-Chain
```

Primary systems:

```text
F frontier-direct
G frontier-same-harness
H hybrid-local-first-with-frontier-escalation
```

The key commercial output is:

```text
verified successful maintenance outcomes / paid inference dollar
```

not raw token reduction.

---

## H3 — longitudinal maintenance lift

On repeated maintenance episodes against the same repository or related repository set, accumulated **verified** memory should improve future outcomes.

Primary comparison:

```text
D local-recursive-memory-reset
E local-recursive-verified-memory-preserved
```

Primary benchmark:

```text
custom longitudinal sequences
```

Use compatible SWE-Chain sequences as a secondary external longitudinal check when the upstream benchmark semantics allow stateful execution without contaminating task validity.

Measure whether performance improves with episode number and whether memory creates harmful negative transfer.

# 5. Pre-registered decision thresholds

These thresholds are project decision rules, not claims of industry consensus.

## H1 pass

Evaluate H1 in layers.

### H1a — deterministic context

`local-deterministic` passes against `local-direct` if at least one holds:

1. verified success improves by **>= 8 percentage points** on the same held-out maintenance tasks; or
2. verified success remains within **5 percentage points** while primary-model context/token cost falls by **>= 30%**; or
3. context/retrieval quality improves materially on Agent Retrieval Bench and produces a corresponding downstream reduction in solver exploration or cost.

### H1b — recursive orchestration

`local-recursive-fallback` passes against `local-deterministic` if at least one holds:

1. verified success improves materially; or
2. cost per verified success improves by **>= 1.5x**; or
3. context selection improves materially with no meaningful degradation in downstream verified success.

### H1c — live 2070 controller

`local-recursive-2070` is promoted over deterministic recursive fallback only if it produces a reproducible incremental benefit in:

- verified outcome;
- cost per verified outcome;
- latency;
- retrieval quality;
- or reduction in primary-model exploration,

without unacceptable negative transfer.

If C1 does not materially beat C0, the deterministic fallback remains the preferred implementation. Do **not** treat “the GPU ran” as a win.

## H2 pass

H2 passes if the hybrid satisfies at least one:

1. verified success is within **5 percentage points** of the frontier baseline while paid frontier inference falls by **>= 50%**; or
2. cost per verified success is **>= 2x better** than the frontier baseline while verified success remains commercially usable; or
3. human intervention minutes per verified task falls materially without higher regression/revert rate.

## H3 pass

H3 passes only if all are true:

1. later episodes show a measurable reduction in attempts, cost, latency, or failure rate relative to memory-reset control;
2. verified success does not degrade;
3. harmful-memory / negative-transfer events stay below **5% of memory-using runs**;
4. beneficial retrieval is traceable to specific admitted evidence, not model self-claims.

## Productization gate

Do not start a standalone commercial control plane because the architecture feels promising.

Productization is justified only when the final report supports one of:

- strong H1 + strong H2;
- strong H2 even if the model-backed recursive controller itself is neutral;
- strong H3 with credible longitudinal compounding;
- strong governed-control-plane value discovered during external pilots despite weak inference differentiation.

A result where **C0 approximately equals C1** is not a failure of the architecture; it means deterministic recursive evidence orchestration is likely preferable to a dedicated 2070 controller.

# 6. Experimental arms

Every scientific arm must run from the same task manifest and exact starting SHA.

| Arm | Context | Memory | Solver | Recursive controller | Frontier escalation |
|---|---|---|---|---|---|
| **A `local-direct`** | ordinary bounded repo/tool context only | off/reset | Qwen Coder 14B | none | no |
| **B `local-deterministic`** | CT103 deterministic preflight + graph/FTS/context pack | off/reset | Qwen Coder 14B | none | no |
| **C0 `local-recursive-fallback`** | deterministic preflight + conditional recursive path | off/reset unless suite says otherwise | Qwen Coder 14B | deterministic/read-only fallback | no |
| **C1 `local-recursive-2070`** | deterministic preflight + conditional recursive path | off/reset unless suite says otherwise | Qwen Coder 14B | live model-backed 2070 | no |
| **D `local-recursive-memory-reset`** | best local recursive strategy from H1 | reset before episode | Qwen Coder 14B | frozen from H1 result | no |
| **E `local-recursive-memory`** | best local recursive strategy from H1 | verified history preserved | Qwen Coder 14B | frozen from H1 result | no |
| **F `frontier-direct`** | provider/native repository exploration where feasible | provider default | frontier coding agent/model | provider native | n/a |
| **G `frontier-same-harness`** | same CT103 context/ACI/sandbox/verification as local arms | experiment-controlled | frontier coding model | experiment-controlled | n/a |
| **H `hybrid`** | deterministic -> conditional local recursion -> frontier only on typed escalation | verified history by suite rule | Qwen 14B first | best frozen local strategy | yes |

### Current-build reality

At V10 start, the production/normal dispatch path may enter the conditional recursive function but remain in `fallback_deterministic` because the live model client is not wired into normal prepare-dispatch.

That is acceptable and becomes **C0**, not C1.

V10 must not mislabel deterministic fallback as a live 2070 result.

### Important

Do not begin recurrent/RWKV/xLSTM/SSM controller experiments until A/B/C0/C1 establish that a model-backed recursive controller adds value.

First prove that:

```text
structured context matters
recursive orchestration matters
a live controller model adds incremental value
```

Only then compare controller backbones:

```text
C1a small-transformer controller
C1b recurrent/RWKV/xLSTM/SSM controller
```

The same task set, budgets, and Qwen patch author must be used.

# 7. Benchmark corpora

V10 uses four core benchmark layers plus one optional sanity layer.

Do **not** rely on a single benchmark to validate the product thesis.

Before adopting any benchmark, verify its current repository/source, license, task semantics, setup requirements, allowed redistribution, and evaluation procedure. Record those facts in `docs/BENCHMARK_LICENSES.md`.

---

## Corpus A — Agent Retrieval Bench

**Purpose:** component-level evaluation of the thing the recursive context worker is supposed to improve: selecting and structuring useful repository evidence before or during patch generation.

Use it to measure, where supported by the benchmark:

```text
relevant-file recall
relevant-file precision
context size / tokens
unnecessary files retrieved
abstention/selectivity
time or tool calls to useful evidence
downstream solver exploration
downstream verified outcome on compatible tasks
```

Primary comparisons:

```text
A vs B
B vs C0
C0 vs C1
```

Do not claim a context-worker win from end-to-end CI alone if retrieval quality itself is worse.

---

## Corpus B — SWE-CI

**Purpose:** primary public end-to-end maintenance/evolution benchmark.

Use SWE-CI as the main external answer to:

> Does this architecture maintain evolving repositories competitively under objective CI/test verification?

Use a staged split:

```text
dev/smoke subset       -> harness debugging only
frozen validation set  -> architecture comparison
held-out test set      -> final reported result
```

Do not tune prompts, routing thresholds, retrieval policy, or verifier behavior on the held-out set.

Primary comparisons:

```text
A / B / C0 / C1
then G / H on the same frozen task subset
```

Scale to the full benchmark only after the harness is stable and compute/spend are understood.

---

## Corpus C — SWE-Chain

**Purpose:** chained dependency/package evolution and repeated upgrade maintenance.

Use SWE-Chain to answer:

```text
Can the system survive sequential dependency/version changes?
Does a prior maintenance outcome help the next transition?
Does the hybrid reduce frontier spend on chained upgrades?
```

Primary comparisons:

```text
best local arms
D vs E where stateful use is semantically valid
G vs H
```

Do not force memory into an upstream task sequence if it would leak future task information or violate benchmark semantics.

---

## Corpus D — custom longitudinal maintenance sequences

**Purpose:** test the proposed moat directly.

Create at least:

- **5 repositories**
- **6–10 ordered maintenance episodes per repository**
- at least one multi-repository dependency/contract sequence if practical

Example sequence:

```text
episode 1  dependency upgrade
episode 2  API break / CI repair
episode 3  second related upgrade
episode 4  SARIF/static finding
episode 5  human rejection or explicitly invalidated hypothesis fixture
episode 6  related maintenance change
episode 7  regression or changed constraint
episode 8  subsequent repair
```

Only evidence that would have existed before an episode may be retrieved for that episode.

Future episode ground truth must never leak into prior memory.

This corpus is the primary H3 test.

---

## Corpus E — optional SWE-bench-family sanity subset

**Purpose:** secondary comparability with broader coding-agent/context-selection literature.

Use only as a supporting sanity check.

Do not optimize V10 around a headline SWE-bench score.

If used:

- select the subset before scoring;
- record exact dataset/version;
- preserve upstream task semantics;
- report that V10 is maintenance-oriented and SWE-bench is not the primary thesis benchmark.

# 8. Evaluation result schema

Create a canonical `maintenance_eval_result.v1`.

Minimum fields:

```json
{
  "schema": "maintenance_eval_result.v1",
  "experiment_id": "...",
  "experiment_version": "...",
  "task_id": "...",
  "episode_index": 1,
  "arm": "local-recursive-2070",
  "repeat_index": 1,

  "benchmark": {
    "name": "SWE-CI|SWE-Chain|Agent-Retrieval-Bench|custom-longitudinal|SWE-bench-family",
    "version": "...",
    "split": "dev|validation|test|custom",
    "upstream_task_id": "...",
    "adapter_version": "...",
    "license_ref": "..."
  },

  "source_repo": "...",
  "starting_sha": "...",
  "policy_source_sha": "...",

  "control_plane_sha": "...",
  "worker_image_digest": "...",
  "ci_image_digest": "...",

  "models": {
    "primary": "...",
    "controller": "...",
    "controller_backend": "none|deterministic|model",
    "frontier": null,
    "quantization": "...",
    "model_config_hash": "..."
  },

  "context": {
    "strategy": "...",
    "recursive_context_required": false,
    "recursive_invoked": false,
    "controller_model_invoked": false,
    "invocation_reasons": [],
    "graph_queries": 0,
    "memory_records_considered": 0,
    "memory_records_used": 0,
    "context_tokens_to_primary": 0,
    "retrieved_files": [],
    "gold_files_available": false,
    "retrieval_precision": null,
    "retrieval_recall": null
  },

  "usage": {
    "local_prompt_tokens": 0,
    "local_completion_tokens": 0,
    "controller_prompt_tokens": 0,
    "controller_completion_tokens": 0,
    "frontier_prompt_tokens": 0,
    "frontier_completion_tokens": 0,
    "frontier_cached_tokens": 0,
    "frontier_cost_usd": 0.0,
    "local_gpu_seconds": 0.0,
    "controller_gpu_seconds": 0.0,
    "wall_seconds": 0.0
  },

  "execution": {
    "solver_attempts": 0,
    "repair_attempts": 0,
    "ci_cycles": 0,
    "files_changed": 0,
    "diff_lines_added": 0,
    "diff_lines_removed": 0
  },

  "verification": {
    "status": "verified|failed|blocked|invalid",
    "verification_claim_ids": [],
    "ci_passed": false,
    "adequacy_passed": false,
    "limitations": []
  },

  "memory": {
    "retrievals": 0,
    "helpful": 0,
    "harmful": 0,
    "stale": 0,
    "negative_transfer": false,
    "evidence_refs": []
  },

  "human": {
    "intervention_minutes": 0.0,
    "accepted": null,
    "modified": null,
    "rejected": null
  },

  "outcome": {
    "verified_success": false,
    "regression_detected": false,
    "reverted": false,
    "failure_class": null
  },

  "run_refs": [],
  "trajectory_refs": [],
  "observatory_refs": []
}
```

Raw secrets, private prompts, hidden chain-of-thought, benchmark hidden-test content, and unredacted provider payloads must not enter the result schema.

# 9. Derived metrics

At minimum compute:

```text
verified_success_rate
first_pass_ci_success_rate
ultimate_ci_success_rate

cost_per_attempted_task
paid_cost_per_verified_task
local_gpu_seconds_per_verified_task
controller_gpu_seconds_per_verified_task
wall_time_per_verified_task

recursive_context_trigger_rate
controller_model_invocation_rate
recursive_trigger_rate_by_reason

frontier_escalation_rate
frontier_tokens_per_verified_task
primary_context_tokens_per_verified_task
controller_tokens_per_verified_task

solver_attempts_per_verified_task
ci_cycles_per_verified_task
human_minutes_per_verified_task

retrieval_precision
retrieval_recall
retrieved_context_tokens
unnecessary_retrieval_rate
solver_exploration_after_context

memory_retrieval_precision_proxy
helpful_memory_rate
stale_memory_rate
harmful_memory_rate
negative_transfer_rate

regression_rate
revert_rate

verified_success_per_paid_dollar
verified_success_per_total_compute_proxy
```

Do not use the existing reward score as the primary outcome.

Primary end-to-end outcome = machine-recorded verified maintenance result.

Primary context-worker outcome = useful evidence selected with lower downstream solver burden, not merely more recursive activity.

# 10. Reproducibility rules

1. Every task starts from an immutable exact SHA.
2. Every experiment has an immutable `experiment_manifest.yaml`.
3. Model identifiers and quantization are pinned.
4. Prompt/template/policy/config hashes are recorded.
5. Context budgets and RLM depth/subcall budgets are pinned.
6. Verification commands are pinned per task.
7. Same task manifests are used across arms unless an arm definition explicitly requires provider-native execution.
8. Local model temperature/sampling settings are pinned.
9. For stochastic arms, use at least **3 repeats per task** when compute permits.
10. Failed infrastructure runs are classified separately from model/task failures.
11. Harness bugs invalidate affected runs; do not silently patch results.
12. Agent behavior changes create a new experiment version.
13. Results are append-only.
14. Analysis scripts consume immutable result files; they do not query mutable live state as ground truth.
15. The experiment manifest is committed before the first scored run.
16. Public benchmark dev/validation/test splits are fixed before scored comparison.
17. Hidden/verification-only benchmark artifacts are never included in model context.
18. Benchmark adapters preserve upstream task intent and record every transformation.
19. C0 and C1 are never conflated: `controller_model_invoked` must prove whether the 2070 model actually ran.
20. A benchmark result is not merged with custom-corpus results into one headline number unless weighting is pre-registered.

---

# 11. Repo layout

Create a separate evaluation repo:

```text
ai-sdlc-lab/maintenance-evals/
  README.md
  LICENSE-or-private-notice.md
  pyproject.toml

  manifests/
    experiments/
      v10-context-ablation.yaml
      v10-maintenance-end-to-end.yaml
      v10-longitudinal.yaml
      v10-frontier-hybrid.yaml
    tasks/
      swe_ci/
      swe_chain/
      agent_retrieval_bench/
      swe_bench_sanity/
      longitudinal/

  schemas/
    maintenance_eval_task.v1.json
    maintenance_eval_result.v1.json
    experiment_manifest.v1.json

  adapters/
    agent_control.py
    swe_ci.py
    swe_chain.py
    agent_retrieval_bench.py
    swe_bench.py

  suites/
    context_ablation.py
    maintenance_end_to_end.py
    frontier_hybrid.py
    longitudinal.py

  fixtures/
    synthetic/
    public_metadata/

  pricing/
    pricing-2026-08.yaml

  analysis/
    summarize.py
    compare.py
    retrieval.py
    longitudinal.py
    negative_transfer.py

  results/
    .gitkeep

  reports/
    .gitkeep

  docs/
    METHODOLOGY.md
    COST_ACCOUNTING.md
    BENCHMARK_LICENSES.md
    BENCHMARK_SPLITS.md
    THREAT_TO_VALIDITY.md
    GO_NO_GO.md
```

Keep platform behavior in `agent-control-plane`.

Keep experiment definition, benchmark adapters, task manifests, result analysis, and reports in `maintenance-evals`.

If a missing control-plane API prevents evaluation, add the smallest generic telemetry/replay interface needed; do not embed benchmark-specific behavior into production workflows.

# 12. Epic spine

```text
T00 -> T00.5 -> T01 -> T02 -> T03 -> T04 -> T05 -> T06 -> T07 -> T08 -> T09 -> T10
```

No ticket may begin before its dependency is Done.

No parallel agent-control-plane mutation.

Analysis-only work may run after the corresponding immutable result set is frozen.

# 13. Ticket ledger

| ID | Slice | Deps | Initial status |
|---|---|---|---|
| **T00** | deployed-baseline certification + stale-doc reconciliation | — | Ready |
| **T00.5** | experimental live 2070 recursive-controller hook + C0/C1 proof | T00 | Blocked |
| **T01** | `maintenance-evals` repo + schemas + pre-registration manifest | T00.5 | Blocked |
| **T02** | exact-SHA replay runner + experiment isolation | T01 | Blocked |
| **T03** | cost/token/GPU/latency telemetry normalization | T02 | Blocked |
| **T04** | benchmark ingestion + licenses + frozen dev/validation/test splits + custom longitudinal corpus | T03 | Blocked |
| **T05** | context ablation A/B/C0/C1 on Agent Retrieval Bench + SWE-CI validation subset | T04 | Blocked |
| **T06** | end-to-end local maintenance on SWE-CI + SWE-Chain | T05 | Blocked |
| **T07** | memory-reset vs verified-memory longitudinal D/E | T06 | Blocked |
| **T08** | frontier direct + same-harness F/G on frozen external tasks | T06 | Blocked |
| **T09** | hybrid H + held-out public replication | T08 | Blocked |
| **T10** | statistical summary + threats + go/no-go report | T09 | Blocked |

# 14. Hard gates

**G1 — trust-boundary truth:** deployed CT103/CT104/CT102 authority matches documentation before freeze.

**G2 — recursive-controller truth:** C0 means deterministic fallback; C1 means a live model-backed controller call is proven by telemetry. Never label fallback as “2070 RLM.”

**G3 — immutable baseline:** control-plane SHA, worker image, models, policies, prompts, budgets, and verifier profiles are frozen before scored runs.

**G4 — benchmark integrity:** benchmark source/version/license/split is recorded before scored execution.

**G5 — no benchmark leakage:** hidden tests, future chain steps, future longitudinal outcomes, or verification-only artifacts cannot enter model context.

**G6 — verification authority:** success comes only from configured machine-recorded verification on the exact result SHA.

**G7 — comparable arms:** all scientific arms use the same starting SHA/task/verifier and differ only by declared experiment variable.

**G8 — cost traceability:** provider cost is calculated from recorded token/credit usage and a versioned price table; local GPU time is recorded separately.

**G9 — no silent tuning:** behavioral changes after results begin force a new experiment version.

**G10 — negative-transfer visibility:** harmful/stale memory is preserved as an outcome, not discarded as an outlier.

**G11 — infrastructure failures separated:** unavailable GPU, runner, network, benchmark setup, or provider is not mislabeled model failure.

**G12 — full provenance:** every report row traces to benchmark/task manifest, run/session, trajectory, verification claim, adapter version, and experiment manifest.

# 15. T00 — deployed-baseline certification + stale-doc reconciliation

## Goal

Prove what is actually deployed before freezing the experiment.

## Required work

In `agent-control-plane`:

1. verify CT103 is the only Gitea mutation authority;
2. verify CT104 has no Gitea write token in the actual runtime;
3. verify CT104 sandbox has no platform/model/state credentials;
4. verify CT102 has no agent-bot/control-plane write token;
5. verify current control-plane and worker image SHAs/digests;
6. run the current deploy-verify smoke;
7. reconcile stale documentation describing transitional CT104 token debt;
8. create `docs/evals/V10_BASELINE.md`.

`V10_BASELINE.md` records:

```text
baseline_tag
agent-control-plane git SHA
CT103 deployed image digest
CT104 deployed image digest
CT102 runner/version
Qwen model identifier
Qwen quantization
2070 controller identifier
Ollama versions
recursive-context budgets
policy hashes
command-registry hash
verification profile/version
Observatory projection version
date/time
known limitations
```

Create Git tag:

```text
eval-baseline-2026-08
```

or a later exact-date equivalent if this epic executes later.

## Acceptance

- [ ] CT104 Gitea write credentials absent in deployed runtime.
- [ ] CT103 brokerage smoke passes.
- [ ] CT102 verification smoke passes.
- [ ] stale token documentation corrected.
- [ ] baseline document committed.
- [ ] baseline tag created.
- [ ] full tests + deploy-verify pass.
- [ ] no agent behavior changed beyond documentation or required correctness fixes.

## Cursor planning prompt

```text
Plan V10 T00 only: deployed-baseline certification and stale-document reconciliation. Inspect the current repo and existing deploy-verify/runbook docs before changing anything. Verify from code/config/docs that CT103 is the sole Gitea mutation authority, CT104 has no Gitea write credentials in the target deployed architecture, CT102 is verification-only, and the sandbox receives no persistent platform/model/state credentials. Identify stale documentation that still describes CT104 transitional write tokens after 6D.2 brokerage was completed. Do not redesign the system. Add docs/evals/V10_BASELINE.md capturing the exact control-plane SHA, deployed image/model/config/policy/verifier identifiers and known limitations. Propose the exact commands a human/deploy-verify session must run to certify the deployed state. Do not execute secret-printing commands. One ticket only.
```

---

# 15A. T00.5 — experimental live 2070 recursive-controller hook

## Goal

Make the already-scaffolded conditional recursive path capable of running in two explicit evaluation modes:

```text
controller_backend=deterministic
controller_backend=model
```

This ticket does **not** make the 2070 an always-on memory manager.

CT103 remains responsible for:

- deterministic preflight;
- `recursive_context_required`;
- budgets;
- policy;
- canonical state;
- memory admission;
- verification;
- publication.

The recursive controller remains read-only and conditional.

## Current-build assumption to verify

Normal prepare-dispatch currently may call the conditional recursive function without a live controller-model client, causing the path to remain `fallback_deterministic`.

Verify this from current code before changing it.

If the assumption is wrong, document the actual behavior and implement only what is missing for clean C0/C1 selection.

## Required work

Introduce the narrowest possible backend selection behind the existing recursive-controller interface, for example:

```yaml
recursive_context:
  enabled: true
  invocation: conditional
  controller_backend: deterministic | model
  controller_role: gpu-2070
```

Requirements:

```text
recursive_context_required=false
    -> no controller call

recursive_context_required=true + deterministic
    -> existing allowlisted read-only fallback plan

recursive_context_required=true + model
    -> live configured 2070 controller call
    -> same typed read-only tool boundary
    -> same CT103 budgets
    -> recursive_context_result.v1
    -> CT103 schema/evidence validation
```

Add telemetry proving:

```text
recursive_context_required
recursive_context_invoked
controller_backend
controller_model_invoked
controller_role
controller_model_id
invocation_reason[]
controller prompt/completion tokens
controller wall/GPU time
stop_reason
```

Do not add recurrent/SSM models in this ticket.

Use the simplest already-supported small model that reliably fits the 2070 for C1.

## Acceptance

- [ ] a simple task with `recursive_context_required=false` makes no 2070 call.
- [ ] the same qualifying test task can run as C0 and C1.
- [ ] C0 produces a valid result with `controller_backend=deterministic` and `controller_model_invoked=false`.
- [ ] C1 demonstrably calls the configured 2070 model and records `controller_model_invoked=true`.
- [ ] both use the same read-only tool contract and CT103-owned budgets.
- [ ] neither can write canonical memory/state/repo or claim verification.
- [ ] CT103 rejects malformed/unsupported recursive results.
- [ ] deploy-verify passes.
- [ ] normal production/default behavior is not silently changed merely for the benchmark.

## Cursor planning prompt

```text
Plan V10 T00.5 only. Inspect the current prepare-dispatch and run_conditional_recursive_context implementation first. Confirm whether the normal live path currently lacks a controller-model client and therefore uses fallback_deterministic. Add the smallest experiment-selectable controller backend so qualifying runs can explicitly use either deterministic fallback (C0) or a live model-backed gpu-2070 controller (C1). Preserve CT103 ownership of deterministic preflight, recursive_context_required, budgets, canonical state, memory admission, policy, verification, and publication. The controller remains conditional, read-only, bounded, and produces recursive_context_result.v1. Add telemetry proving whether the 2070 model actually ran. Do not add recurrent/SSM models, change the default authority model, or make recursion always-on.
```

---

# 16. T01 — evaluation repo + schemas + pre-registration

## Goal

Create the experiment boundary before implementing the runner.

## Human step

Create private Gitea repo:

```text
ai-sdlc-lab/maintenance-evals
```

No platform write credentials in this repo.

## Required work

Create the repo layout from §11.

Implement and test:

- `maintenance_eval_task.v1`
- `maintenance_eval_result.v1`
- `experiment_manifest.v1`

Create `docs/METHODOLOGY.md`.

Create pre-registration manifests with:

- benchmark names/versions/splits (or placeholders explicitly resolved in T04 before scoring);
- hypotheses;
- arm definitions;
- task inclusion/exclusion rules;
- thresholds from §5;
- metrics;
- repeat counts;
- random/sampling config;
- frozen model identifiers;
- maximum per-task budget;
- infrastructure-failure policy;
- invalid-run policy.

The manifest must be hashable and immutable after the first scored run.

## Acceptance

- [ ] schemas validate fixtures.
- [ ] manifest includes H1/H2/H3 and thresholds before results exist.
- [ ] no result code can mutate the experiment manifest.
- [ ] no secrets or private/employer data.
- [ ] unit tests pass.

## Cursor planning prompt

```text
Plan V10 T01 only in the new ai-sdlc-lab/maintenance-evals repo. Create an evaluation-only Python package and the directory structure defined by the V10 ledger. Implement JSON schemas and typed Python models for maintenance_eval_task.v1, maintenance_eval_result.v1, and experiment_manifest.v1. Add immutable experiment manifests for local ablation, frontier/hybrid, and longitudinal experiments. Pre-register hypotheses, thresholds, metrics, repeats, budgets, invalid-run policy, and task inclusion rules before any scored execution exists. Add docs/METHODOLOGY.md and tests. Do not implement the task runner yet. Do not add model/provider credentials. One ticket only.
```

---

# 17. T02 — exact-SHA replay runner

## Goal

Make every task repeatable from a clean state.

## Flow

```text
task manifest
  -> resolve exact source SHA
  -> create unique eval run id
  -> prepare isolated fresh workspace
  -> configure declared arm
  -> reset/seed memory according to arm
  -> dispatch existing agent-control-plane path
  -> wait for terminal session
  -> collect patch/result SHA
  -> collect CT102 verification claim
  -> emit maintenance_eval_result.v1
  -> destroy workspace
```

## Required behavior

CLI:

```text
evalctl run --experiment <manifest> --task <task_id> --arm <arm>
evalctl replay --result <result.json>
evalctl validate-run --result <result.json>
```

The runner must not directly patch the target repository.

It orchestrates the existing platform and records outcomes.

For memory-reset arms, use a namespaced experimental memory view or isolated copied state. Do not delete production/audit history.

## Acceptance

- [ ] same starting SHA guaranteed.
- [ ] unique isolated workspace per run.
- [ ] result links exact session/run/verification refs.
- [ ] memory isolation is deterministic.
- [ ] failed teardown marks run invalid/infrastructure failure.
- [ ] replay command reconstructs the declared inputs.
- [ ] no target-repo privileged workflow added.

## Cursor planning prompt

```text
Plan V10 T02 only in maintenance-evals. Implement an exact-SHA evaluation runner that drives the existing agent-control-plane rather than reimplementing agent behavior. Each run must create an immutable eval run id, start from the task manifest's exact SHA, use an isolated fresh workspace, configure the declared experiment arm, apply memory-reset/preserve policy without deleting audit history, dispatch through the existing trusted control-plane path, wait for a terminal AgentSession, collect the exact result SHA and verification claims, and emit maintenance_eval_result.v1. Add evalctl run/replay/validate-run. Classify infrastructure failures separately. Do not implement pricing or public benchmarks yet.
```

---

# 18. T03 — usage and cost telemetry normalization

## Goal

Make cost comparisons auditable.

## Required work

Normalize from existing session/trajectory/provider metadata:

- local prompt/completion tokens;
- primary-model context tokens;
- recursive trigger counts and trigger reasons;
- controller backend and whether a live model controller was invoked;
- controller prompt/completion tokens;
- recursive subcall counts;
- recursive depth/query counts;
- primary and controller GPU wall/inference seconds where available;
- frontier prompt/output/cache usage;
- frontier cost;
- total wall time;
- solver attempts;
- repair attempts;
- CI cycles.

Create:

```text
pricing/
  pricing-2026-08.yaml
```

Price table fields:

```text
provider
model
effective_from
input_per_million
cached_input_per_million
output_per_million
credit_conversion_if_applicable
source_note
```

Do not hard-code pricing into analysis.

Provider price changes create a new versioned table, not rewritten historical results.

Local compute must remain separately reported from paid API cost.

## Acceptance

- [ ] one result can be recomputed from raw usage + versioned price table.
- [ ] missing usage is explicit, not treated as zero.
- [ ] local GPU seconds recorded independently.
- [ ] recursive context usage visible separately from primary solver usage.
- [ ] deterministic fallback and live 2070 controller usage cannot be conflated.
- [ ] recursive trigger rate and trigger reasons are recoverable.
- [ ] Observatory/result links remain safe-display only.
- [ ] unit tests pass.

## Cursor planning prompt

```text
Plan V10 T03 only. Extend maintenance-evals so each result normalizes local-model usage, recursive-context usage, frontier usage, wall time, attempts, and CI cycles from existing session/trajectory artifacts. Add a versioned pricing YAML and a deterministic cost calculator. Never hard-code model prices into analysis code and never treat unknown usage as zero. Keep local GPU seconds separate from paid API dollars. Do not change model routing or agent behavior.
```

---

# 19. T04 — benchmark ingestion + frozen splits + longitudinal corpus

## Goal

Make known public benchmarks first-class experiment inputs before scored architecture comparison.

## Public benchmark targets

Integrate, subject to verified source/license/setup:

```text
Agent Retrieval Bench
SWE-CI
SWE-Chain
optional SWE-bench-family sanity subset
```

Before cloning/downloading/adopting any benchmark, populate `docs/BENCHMARK_LICENSES.md` with:

```text
name
source/repository or dataset id
version/commit/date
license
redistribution constraints
task semantics
verification semantics
hidden-test handling
network/setup requirements
known incompatibilities
adapter transformations
```

Create `docs/BENCHMARK_SPLITS.md`.

For each public benchmark, predeclare:

```text
dev/smoke tasks
validation tasks
held-out test tasks
```

Do not inspect held-out outcomes while tuning the harness or architecture.

## Adapter requirements

Every adapter converts upstream tasks to `maintenance_eval_task.v1` and records:

```text
benchmark_name
benchmark_version
upstream_task_id
upstream_repo
starting_sha
task_text/source
verification reference
adapter_version
transformations
known limitations
```

Do not silently rewrite upstream task intent.

## Custom longitudinal corpus

Also create:

```text
>= 5 repositories
6–10 ordered maintenance episodes per repository where practical
```

Include:

- repeated failure fingerprint;
- previously rejected hypothesis;
- verified repair strategy;
- stale/superseded memory;
- contradiction/invalidation;
- at least one harmful-memory trap;
- at least one cross-repo or dependency-path task if practical.

Future evidence must not leak backward.

## Acceptance

- [ ] benchmark sources/licenses/version are documented.
- [ ] adapters preserve task intent.
- [ ] dev/validation/test split frozen before T05.
- [ ] exact SHAs pinned where applicable.
- [ ] verification defined before execution.
- [ ] hidden tests/answers are not model context.
- [ ] custom longitudinal future evidence cannot leak backward.
- [ ] no employer/private fixtures.
- [ ] corpus/adapters tagged before scored T05.

## Cursor planning prompt

```text
Plan V10 T04 only. Integrate the benchmark layer before any scored architecture comparison. Verify and document the current source, version, license, task semantics, verification semantics, hidden-test handling, setup/network requirements, and adapter transformations for Agent Retrieval Bench, SWE-CI, SWE-Chain, and an optional small SWE-bench-family sanity subset. Create frozen dev/validation/held-out splits before scoring. Implement narrow adapters to maintenance_eval_task.v1 without changing task intent. Also create the custom longitudinal corpus with at least five repositories and ordered episodes testing useful, rejected, stale, superseded, contradictory, and harmful memory. Do not run scored experiments yet and do not use employer/private data.
```

# 20. T05 — context ablation A/B/C0/C1

## Goal

Answer H1 and determine whether a live 2070 controller adds value beyond deterministic context and deterministic recursive orchestration.

## Benchmarks

Primary:

```text
Agent Retrieval Bench validation split
```

Downstream check:

```text
frozen SWE-CI validation subset
```

## Arms

```text
A  local-direct
B  local-deterministic
C0 local-recursive-fallback
C1 local-recursive-2070
```

Keep fixed:

- Qwen Coder 14B patch-author model;
- quantization;
- sampling;
- task;
- source SHA;
- verifier;
- patch budget;
- tool policy;
- max attempts;
- recursive trigger logic and budgets between C0/C1.

Only the declared context/controller strategy changes.

## Required context analysis

For Agent Retrieval Bench-compatible tasks, collect:

```text
relevant-file precision/recall where gold labels exist
retrieved context size
unnecessary retrieval
graph/tool query count
recursive trigger reason
controller invocation
time to useful evidence
downstream solver exploration where measurable
```

For SWE-CI validation tasks, collect the normal verified maintenance metrics.

## Run rule

Use paired tasks.

If feasible:

```text
>= 3 repeats / task / arm
```

If compute makes that impractical, document reduced repeat count before scored execution.

Do not inspect aggregate outcome comparisons until the committed run batch is complete.

## Acceptance

- [ ] all four arms complete on the frozen validation subsets.
- [ ] telemetry proves C0 never called the model controller and C1 did when the recursive branch triggered.
- [ ] context/retrieval metrics generated for Agent Retrieval Bench.
- [ ] downstream verified metrics generated for SWE-CI validation.
- [ ] invalid/infrastructure runs classified separately.
- [ ] no behavior tuning during batch.
- [ ] result set hash/tag recorded.
- [ ] H1a/H1b/H1c metrics generated mechanically.

## Cursor planning prompt

```text
Plan V10 T05 only. Run the frozen context ablation across A local-direct, B local-deterministic, C0 local-recursive-fallback, and C1 local-recursive-2070. Use Agent Retrieval Bench as the primary component benchmark and a frozen SWE-CI validation subset as the downstream maintenance check. Keep the Qwen patch author, quantization, sampling, verifier, SHAs, tool policy, budgets, trigger logic, and attempt limits fixed. C0 and C1 must differ only in deterministic versus live model-backed recursive controller. Collect retrieval precision/recall where available, context size, unnecessary retrieval, tool/query counts, trigger reasons, controller invocation, solver exploration, and verified outcome. Freeze the raw result set before comparative interpretation.
```

# 21. T06 — end-to-end local maintenance on SWE-CI + SWE-Chain

## Goal

Determine whether the local architecture works on known maintenance/evolution benchmarks, not only context-selection tasks.

## Benchmarks

```text
SWE-CI frozen validation/test progression
SWE-Chain frozen compatible subset
```

## Arms

At minimum:

```text
A  local-direct
B  local-deterministic
C0 local-recursive-fallback
C1 local-recursive-2070
```

If T05 clearly shows one recursive implementation is dominated, do not silently drop it from the pre-registered T06 set. Either:

- run the originally registered arms; or
- version the T06 experiment manifest before execution and explain the gate.

## Required analysis

Per benchmark and arm:

```text
verified success
first-pass and ultimate CI success
solver attempts
CI cycles
context tokens
controller usage
wall time
local GPU seconds
failure class
```

Do not combine SWE-CI and SWE-Chain into one headline success percentage.

## Acceptance

- [ ] benchmark-specific result sets are frozen separately.
- [ ] task setup/verification failures are separated from model failures.
- [ ] no hidden benchmark artifacts enter model context.
- [ ] C0/C1 controller truth remains auditable.
- [ ] best local strategy for T07/T09 is selected only after the frozen T06 analysis.

## Cursor planning prompt

```text
Plan V10 T06 only. Run end-to-end local maintenance evaluation on the frozen SWE-CI and SWE-Chain subsets using the pre-registered local arms. Preserve upstream task semantics and hidden-test boundaries. Report benchmark-specific verified success, CI success, attempts, context/controller usage, tokens, latency, GPU time, and failure classes. Do not merge the two benchmarks into one score and do not tune the agent during the batch. Freeze each result set before choosing the best local strategy for later longitudinal/hybrid work.
```

# 22. T07 — longitudinal memory D/E

## Goal

Answer H3.

## Arms

```text
D local-recursive-memory-reset
E local-recursive-memory
```

Use the best **frozen local context/controller strategy** selected from T05/T06.

Run ordered custom longitudinal sequences.

Where SWE-Chain semantics permit a stateful comparison without contaminating benchmark validity, add a secondary D/E analysis there. Custom longitudinal sequences remain the primary H3 test.

For D:

- preserve immutable audit for reproducibility;
- prevent reusable memory from prior episodes from being available to the current episode.

For E:

- allow only memory that passed normal admission;
- preserve validity/staleness/invalidation semantics;
- no manually curated answer hints.

## Required analysis

For every episode, capture:

```text
episode_index
prior verified episodes available
retrieved memory ids
helpful/harmful/stale labels
attempts
cost
tokens
latency
verified success
failure class
```

Plot/analyze outcome versus episode index.

Negative transfer is a first-class outcome.

## Acceptance

- [ ] future evidence cannot leak backward.
- [ ] D/E differ only in reusable-memory availability.
- [ ] harmful/stale retrieval is retained, not filtered from analysis.
- [ ] every claimed helpful memory cites evidence.
- [ ] custom longitudinal H3 metrics generated.
- [ ] any SWE-Chain memory analysis is clearly marked secondary and benchmark-compatible.

## Cursor planning prompt

```text
Plan V10 T07 only. Execute the frozen longitudinal suites comparing D memory-reset against E verified-memory-preserved using the best frozen local context/controller strategy from T05/T06. Preserve immutable audit history in both arms, but isolate reusable memory so D cannot consume prior-episode reusable memory. E may use only normally admitted evidence-backed memory with existing validity, staleness, contradiction, and invalidation rules. Prevent future-episode leakage. Record exact retrieved memory ids and classify helpful, harmful, stale, and negative-transfer outcomes. Use custom longitudinal sequences as the primary H3 test; add SWE-Chain stateful analysis only where its semantics remain valid.
```

# 23. T08 — frontier baselines F/G

## Goal

Create two honest frontier comparisons on the same frozen public maintenance tasks.

## Benchmarks

Use the same frozen task subsets from:

```text
SWE-CI
SWE-Chain
```

Optionally include a small Agent Retrieval Bench downstream subset only if the frontier system exposes comparable context/retrieval behavior.

## F — frontier direct

Representative market baseline.

Give the frontier coding agent/model the task in its normal supported repository workflow where feasible.

Record limitations where the provider cannot be made strictly equivalent to the local harness.

## G — frontier same harness

Scientific baseline.

Use the same:

- CT103 policy;
- ACI/tool contract;
- sandbox;
- starting SHA;
- context budget where feasible;
- CT102 verification;
- patch/attempt limits.

Only replace the solver/model.

## Human prerequisites

- configure provider API/BYOK credentials through existing secret boundaries;
- set a hard experiment spend cap;
- confirm the exact frontier model/version.

Never commit provider keys.

## Acceptance

- [ ] F and G model/version pinned.
- [ ] spend cap enforced.
- [ ] provider usage captured.
- [ ] F limitations documented.
- [ ] G uses the same verifier and source SHA as local arms.
- [ ] benchmark-specific frontier result sets frozen separately.

## Cursor planning prompt

```text
Plan V10 T08 only. Add frontier baselines F and G on the same frozen SWE-CI and SWE-Chain task subsets used by the local evaluation. F is a representative provider-native/direct coding-agent baseline with deviations explicitly documented. G uses the same CT103 policy/ACI/sandbox/exact-SHA/CT102 verification path while replacing the solver with the pinned frontier model. Add hard per-run and total spend caps without handling or printing secrets. Capture provider usage and freeze benchmark-specific result sets.
```

# 24. T09 — hybrid H + held-out public replication

## Goal

Test the commercial architecture and then replicate the result on held-out public tasks.

## Fixed route

```text
deterministic preflight
  -> local Qwen direct when sufficient
  -> conditional recursive context when declared triggers fire
  -> local Qwen repair
  -> independent verification
  -> frontier escalation only for a typed unresolved condition
```

Use the best frozen local recursive strategy from T05/T06:

```text
deterministic fallback if C0 dominates or ties C1
live 2070 model controller only if C1 earned adoption
```

Frontier escalation may not occur merely because a local answer "looks weak".

Allowed typed escalation triggers should be pre-registered, e.g.:

```text
local attempt budget exhausted with remaining eligible repair
contradictory evidence unresolved after bounded recursion
context overflow unresolved by bounded context strategy
cross-repo ambiguity above configured threshold
verification failure with a distinct unresolved failure fingerprint
explicit policy-approved frontier escalation class
```

Frontier receives a bounded evidence packet, not necessarily the full historical context.

## Held-out replication

After the hybrid policy is frozen, run the untouched held-out sets declared in T04.

Priority:

```text
SWE-CI held-out
SWE-Chain held-out/compatible chain tasks
Agent Retrieval Bench held-out for applicable context comparisons
optional SWE-bench-family sanity subset
```

Do not tune after seeing held-out results.

## Acceptance

- [ ] escalation policy committed before scored H runs.
- [ ] local recursive strategy was selected from frozen prior results, not ad hoc per task.
- [ ] no hidden/manual routing during run.
- [ ] escalation reason recorded.
- [ ] local/controller/frontier tokens and cost separated.
- [ ] H uses the same source SHA and verifier as comparison arms.
- [ ] held-out subsets were declared before result inspection.
- [ ] H2 metrics generated on held-out public tasks.

## Cursor planning prompt

```text
Plan V10 T09 only. Implement and run the pre-registered hybrid arm H using the best frozen local context/controller strategy from T05/T06. Route deterministic preflight -> local Qwen -> conditional recursive context -> verification -> frontier escalation only when a typed pre-registered unresolved condition fires. Do not use subjective self-confidence or manual per-task routing. Record exact escalation reasons and separate local/controller/frontier usage. Then run the untouched held-out public sets declared in T04, prioritizing SWE-CI and SWE-Chain and using Agent Retrieval Bench where applicable. Do not tune after held-out results are visible.
```

# 25. T10 — final analysis and go/no-go

## Goal

Produce the decision document, not another feature.

## Required reports

Generate:

```text
reports/V10_RESULTS.md
docs/THREAT_TO_VALIDITY.md
docs/GO_NO_GO.md
```

`V10_RESULTS.md` must report results **per benchmark** before any cross-benchmark synthesis.

Include:

- benchmark versions, splits, task counts, and exclusions;
- infrastructure/setup failure counts;
- Agent Retrieval Bench context/retrieval metrics;
- SWE-CI verified maintenance results;
- SWE-Chain chained-upgrade results;
- optional SWE-bench-family sanity results;
- custom longitudinal D/E results;
- verified success per arm;
- confidence intervals or bootstrap ranges where practical;
- paid cost / attempted task;
- paid cost / verified task;
- local/controller GPU seconds;
- wall time;
- recursive-context trigger rate;
- controller-model invocation rate;
- trigger-rate breakdown by reason;
- frontier escalation rate;
- context/token usage;
- attempts and CI cycles;
- human intervention if measured;
- memory helpful/harmful/stale/negative-transfer metrics;
- longitudinal episode curves;
- failure taxonomy.

Explicitly answer the component questions:

```text
A -> B: did deterministic context help?
B -> C0: did recursive deterministic orchestration help?
C0 -> C1: did a live 2070 controller add incremental value?
D -> E: did verified memory compound?
G -> H: did hybrid routing reduce paid frontier cost at comparable quality?
```

`THREAT_TO_VALIDITY.md` must discuss at least:

- small sample size;
- home-authored longitudinal fixtures;
- benchmark contamination risk;
- adapter fidelity;
- provider-native baseline inequivalence;
- local hardware effects;
- verifier coverage limits;
- stochasticity;
- benchmark hidden-test/setup differences;
- pricing volatility;
- model updates;
- possible overfitting to current Qwen;
- human-label subjectivity for helpful/harmful memory.

`GO_NO_GO.md` must answer:

```text
Did H1a pass?
Did H1b pass?
Did H1c pass?
Did H2 pass?
Did H3 pass?

What result is strongest?
What result falsified a prior belief?
Is deterministic context a meaningful advantage?
Is recursive orchestration a meaningful advantage?
Does the live 2070 controller earn its cost/complexity?
Is cost routing a meaningful differentiator?
Does memory compound?
Is negative transfer controlled?
Do effects replicate on public held-out tasks?
What should be open-sourced?
What belongs in a standalone product?
What should be abandoned?
```

## Decision branches

### GO — recursive/economic thesis

Proceed to a standalone product extraction epic if H2 is strong and/or H3 shows credible compounding, with the winning local context strategy.

The winning strategy may be C0. Do not force C1 into the product.

### GO — control plane, not recursive-controller moat

If C1 is weak but deterministic context, verification, routing, or orchestration materially improves outcomes, preserve the product thesis around:

```text
WorkItem -> policy -> evidence selection -> agent backend -> VerifiedChange
```

### NO-GO — standalone SaaS

If frontier direct is cheap/reliable enough, public benchmark effects are weak, H3 is weak, and integrations dominate value, do not immediately build a SaaS.

Keep the system as:

- research platform;
- evaluation harness;
- portfolio artifact;
- regulated-agent control-plane toolkit;
- consulting accelerator.

## Acceptance

- [ ] report generated from immutable result files.
- [ ] results presented per benchmark.
- [ ] thresholds evaluated exactly as pre-registered.
- [ ] failures and null results retained.
- [ ] C0/C1 distinction preserved.
- [ ] vendor/provider limitations stated.
- [ ] no post-hoc threshold changes.
- [ ] explicit next-epic recommendation.

## Cursor planning prompt

```text
Plan V10 T10 only. Analyze the immutable V10 result sets and generate reports/V10_RESULTS.md, docs/THREAT_TO_VALIDITY.md, and docs/GO_NO_GO.md. Report Agent Retrieval Bench, SWE-CI, SWE-Chain, custom longitudinal, and optional SWE-bench-family results separately before synthesis. Evaluate H1a/H1b/H1c/H2/H3 exactly as pre-registered. Explicitly compare A->B, B->C0, C0->C1, D->E, and G->H. Include retrieval quality, verified success, cost per attempted and verified task, recursive trigger rate, live-controller invocation rate, controller/local/frontier usage, GPU time, latency, attempts, CI cycles, memory helpful/harmful/stale/negative-transfer metrics, longitudinal curves, held-out replication, and failure taxonomy. Preserve null/negative results. Finish with an explicit recommendation and do not force the 2070 model controller into the product if deterministic recursion performs as well or better.
```

# 26. Deploy-verify template for V10 control-plane changes

Use the repository's existing `DEPLOY_VERIFY_TEMPLATE` where available. V10 adds these evaluation-specific checks.

After any ticket that changes `agent-control-plane`:

```text
1. Local/unit:
   - ruff clean
   - pytest pass
   - schema tests pass

2. CT103:
   - deploy exact intended SHA/image
   - /readyz acceptable
   - Redis/state reachable
   - mutation brokerage smoke passes
   - policy/config hashes match expected baseline unless ticket intentionally versions them

3. CT104:
   - deploy exact intended worker image
   - sandbox capability self-test passes
   - no persistent Gitea/model/state credentials in sandbox
   - fresh workspace + teardown smoke passes

4. CT102:
   - CI verification smoke passes
   - no deploy/agent-bot authority introduced

5. Evaluation:
   - one non-scored smoke task produces maintenance_eval_result.v1
   - if the task triggers recursive context, C0/C1 telemetry proves which backend ran
   - run links to AgentSession, trajectory, verification claim, and Observatory
   - no scored result directory modified by deploy-verify

6. Freeze:
   - record resulting git SHA/image digest
   - if behavioral baseline changed, bump experiment version before scored runs
```

No ticket is Done until deploy-verify evidence is recorded.

---

# 27. Human-only actions

Cursor must not autonomously:

- create or rotate real provider API keys;
- change Gitea admin/token settings;
- expose new public network services;
- approve spend;
- weaken sandbox/network policy;
- merge agent-generated policy/workflow/ADR changes;
- adopt or redistribute benchmark assets without presenting the verified license/source for human review;
- publish benchmark results;
- upload private repositories;
- use employer/company artifacts in the evaluation.

Human provides:

- provider credentials through existing secret management;
- experiment spend cap;
- approval of public benchmark license/use;
- final decision on publishing results.

---

# 28. Suggested run order

Do not jump directly to a full benchmark x arm matrix.

## Harness smoke

```text
2 non-scored tasks
A/B/C0/C1 where compatible
1 repeat
```

Purpose: prove replay, verification, and controller telemetry.

## Benchmark dev smoke

```text
small Agent Retrieval Bench dev subset
small SWE-CI dev subset
small SWE-Chain dev subset
```

Purpose: debug adapters/setup only.

No results from dev smoke are part of final claims.

## Context validation batch

```text
Agent Retrieval Bench validation
+ SWE-CI validation subset
A/B/C0/C1
```

Purpose: decide H1a/H1b/H1c and whether C1 earns use.

## End-to-end local batch

```text
SWE-CI
SWE-Chain
pre-registered local arms
```

Purpose: establish local maintenance capability.

## Longitudinal batch

```text
custom ordered sequences
D/E
```

Optional compatible SWE-Chain stateful check.

## Frontier batch

```text
F/G
same frozen SWE-CI/SWE-Chain tasks
```

## Hybrid + held-out batch

```text
H
same frozen tasks
then untouched held-out public splits
```

No tuning after held-out results are visible.

## Optional sanity batch

```text
small predeclared SWE-bench-family subset
```

Supporting comparability only; not the primary product thesis.

# 29. Analysis conventions

Prefer paired comparisons because the same tasks are run across arms.

At minimum report:

```text
n
mean
median
success proportion
absolute delta
relative cost ratio
bootstrap confidence interval where practical
```

For cost distributions, report median and p90 as well as mean.

Do not claim statistical significance from tiny samples.

Use plots only when generated from immutable result files.

Recommended plots:

```text
Agent Retrieval Bench retrieval precision/recall vs context tokens
solver exploration vs retrieved context by arm
SWE-CI verified success vs paid cost by arm
SWE-Chain chain progress / verified transitions by arm
paid cost per verified task by benchmark and arm
recursive trigger rate and trigger reasons
C0 vs C1 controller incremental value
frontier token usage by arm
latency vs verified success
episode index vs cost for D/E
episode index vs verified success for D/E
helpful/harmful memory rate by episode
failure-class distribution
```

---

# 30. Experiment integrity rules for Cursor

Cursor must follow these during the epic:

```text
One ticket per wave.
Plan before code.
Read existing implementation before adding abstractions.
Do not refactor unrelated code.
Do not optimize the evaluated agent after scored runs begin.
Do not delete failed runs.
Do not rerun only failures and merge them with first-attempt results.
Do not manually choose "better" outputs.
Do not change verification commands after seeing generated patches.
Do not change task text after seeing model behavior.
Do not leak future longitudinal evidence.
Do not expose benchmark hidden tests or future chain steps to the agent.
Do not tune on the held-out public benchmark split.
Do not treat recursive invocation itself as success.
Do not label fallback_deterministic as a live 2070 run.
Do not treat token reduction without verified quality as a win.
Do not treat CI pass outside the configured verification scope as universal correctness.
Do not expose chain-of-thought in Observatory or eval artifacts.
Do not add private/customer/employer data.
```

---

# 31. Epic definition of done

V10 is complete when:

1. deployed baseline is reconciled and frozen;
2. C0 deterministic fallback and C1 live 2070 controller can be selected and distinguished by telemetry;
3. `maintenance-evals` exists with immutable schemas/manifests;
4. exact-SHA task replay is reliable;
5. cost/usage telemetry is reproducible;
6. Agent Retrieval Bench, SWE-CI, and SWE-Chain sources/licenses/adapters/splits are documented and frozen;
7. custom longitudinal corpus is frozen;
8. A/B/C0/C1 context ablation is complete;
9. SWE-CI and SWE-Chain end-to-end local evaluation is complete;
10. D/E longitudinal memory evaluation is complete;
11. F/G frontier baselines are complete on the same frozen public tasks;
12. H hybrid escalation evaluation is complete;
13. untouched held-out public replication is complete;
14. H1a/H1b/H1c/H2/H3 are decided against pre-registered thresholds;
15. recursive trigger rate and live-controller incremental value are explicitly quantified;
16. negative transfer is explicitly quantified;
17. `V10_RESULTS.md`, `THREAT_TO_VALIDITY.md`, and `GO_NO_GO.md` are committed;
18. the next epic is chosen based on evidence rather than architecture preference.

# 32. What comes after V10

Do not pre-commit to V11 implementation before V10 closes.

Potential next branches:

```text
A. Standalone VerifiedChange product extraction
   if economic/longitudinal thesis is strong on held-out public tasks

B. Vendor-neutral governed execution control plane
   if verification/evidence selection/orchestration wins but a live controller does not

C. Controller-backbone research
   only if C1 clearly beats C0 and controller choice still matters

D. External pilot / GitHub adapter
   if technical results are strong enough to justify demand testing

E. Stop commercial product work
   if frontier baselines dominate and longitudinal memory does not compound
```

The result of V10, not the existence of the current architecture, chooses the branch.
