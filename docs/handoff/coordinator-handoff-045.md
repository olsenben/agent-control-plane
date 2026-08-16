# Handoff — coordinator-handoff-045

## Meta

| Field | Value |
|---|---|
| Handoff ID | 045 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T10 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` (unchanged, not amended) |
| ACP change | Documentation only (`boss-ledger-v10.md`, this handoff, `docs/evals/V10_GO_NO_GO.md`) |
| Status | Done (partial analysis on frozen partial evidence); **epic `blocked_waiting_human`** |
| `stopped_reason` | `ticket_done_partial_analysis_epic_blocked_waiting_human` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-045.md
ticket: T10
status: Done (partial analysis); epic blocked_waiting_human (not complete)
epic_status: blocked_waiting_human
experiment_freeze: v10-experiment-freeze-2026-08-16
experiment_version: 1.1.0-t04-frozen
platform_freeze: eval-baseline-2026-08 at 2532de7cf5098baa461e49b92e0d338c089cff45
analysis_inputs: results/v10-t05..t09 frozen sets; coordinator-handoff-034..044; V10_BASELINE.md; docs/benchmarks/*
reports_written: reports/V10_RESULTS.md, docs/THREAT_TO_VALIDITY.md, docs/GO_NO_GO.md, reports/DEEPER_EVAL.md, reports/LITERATURE_COMPARISON.md
acp_written: docs/evals/V10_GO_NO_GO.md, docs/handoff/boss-ledger-v10.md, docs/handoff/coordinator-handoff-045.md
hypotheses_decided: 0 / 5
h1a: unclaimed
h1b: unclaimed
h1c: unclaimed
h2: unclaimed
h3: instrument_verified_outcome_unclaimed
thresholds_evaluated: 0
primary_tests_run: 0
holm_adjustment_applied: false
go_no_go: HOLD
standalone_saas: not_a_GO
epic_32_branch_selected: none
epic_32_closest_unearned: B (vendor-neutral governed control plane)
open_blockers: MATERIALIZE_LICENSED_CORPORA, FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE, EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS, MISSING_PROVIDER_CREDENTIALS, MISSING_SPEND_CAP
literature_verified: arXiv:2607.24882, arXiv:2603.03823, arXiv:2605.14415, arXiv:2506.09289, SWE-bench ICLR 2024 (OpenReview VTF8yNQM66 / arXiv:2310.06770)
literature_defect_found: frozen SWE-CI metric named ANC is EvoScore at gamma=1; V10 ANC must not be compared to a published EvoScore
literature_not_researched: negative transfer / continual learning (DEEPER_EVAL L1)
result_sets_read: 836086c8, 1750165e, 6f2fe308, fdd821bf, e3eba0ed
new_result_sets_created: none
freeze_amended: false
tests: not run (documentation-only ticket; no Python changed)
ruff: not run (documentation-only ticket; no Python changed)
deploy_verify: N/A (no ACP runtime code, model routing, policy, image, or credential changed)
epic_done_items_met: 1-7 met; 8-16 unmet; 17 met; 18 deferred to human gates
next_ticket_id: none available to an agent
stopped_reason: ticket_done_partial_analysis_epic_blocked_waiting_human
```

## What T10 was asked to do, and what it refused to do

T10 analyzed the frozen partial evidence and produced the three epic-mandated
reports plus two supporting documents. It did **not** promote any harness batch
into a result, did not evaluate a pre-registered threshold against a null
endpoint, did not run the statistical plan on zero outcomes, and did not select
an epic section 32 branch.

The single most important line in the whole deliverable set: **zero of five
hypotheses are decided, and the four synthetic harness batches are evidence about
the instrument, not about agent performance.** Every frozen record already says
so in its own `claim_scope` field; T10 treated that field as a contract.

## Documents produced

In `ai-sdlc-lab/maintenance-evals`:

- `reports/V10_RESULTS.md` — three tiers of evidence kept separate, the frozen
  result-set inventory with digests, per-benchmark sections (four of five empty),
  the five component questions A→B, B→C0, C0→C1, D→E, G→H each answered "not
  measurable" with its reason, metric-coverage table against the epic's T10
  requirements, hypothesis status, and the six things the partial evidence does
  establish.
- `docs/THREAT_TO_VALIDITY.md` — replaces the `RESOLVE_IN_T10` stub. Threats that
  already bite are separated from threats that apply to the next execution. Leads
  with the four confounds named in the T10 brief: `agent_execution=false`,
  WaitingHuman corpora, the provisional C0 strategy as a frozen inheritance, and
  external OpenAI failover as an unmeasured routing confound. Also covers the
  dual freeze's obstructive direction, and every item the epic's T10 section
  requires.
- `docs/GO_NO_GO.md` — replaces the `RESOLVE_IN_T10` stub. Answers all 15
  required questions, maps epic section 32 branches A–E against evidence, and
  records the decision.
- `reports/DEEPER_EVAL.md` — 16 items, each cited to the sealed handoff, deploy
  record, or frozen artefact that deferred it.
- `reports/LITERATURE_COMPARISON.md` — accurate citations with comparison rules
  fixed in advance of any result.

In `agent-control-plane`:

- `docs/evals/V10_GO_NO_GO.md` — pointer summary for platform readers.
- `docs/handoff/boss-ledger-v10.md` — epic status, hypothesis status block, open
  human gates, T10 row, wave 14.

## The decision

**HOLD.** No epic section 32 branch may be selected.

- **Branch A (standalone product extraction) cannot be a GO.** The productization
  gate requires strong H1 plus strong H2, or strong H2 alone, or strong H3 with
  credible compounding. Zero hypotheses are decided.
- **A NO-GO would be equally unsupported.** Its antecedents — cheap reliable
  frontier direct, weak public benchmark effects, weak H3 — are also unmeasured.
- **Branch B is closest to the evidence and still unearned.** The "live
  controller does not win" half is untested rather than established, and the
  "verification and orchestration win" half has suggestive engineering evidence
  and no comparative outcome. It is the branch a reader would reach for, which is
  exactly why it must not be claimed.

## Findings worth a coordinator's attention

1. **The dual-metric rule earned its place on real execution.** In 3 of 3 T07
   trap episodes a misapplied prior repair passed the official check and failed
   the frozen V10 additional checks. On the official signal alone, negative
   transfer would have scored as success — the UTBoost failure mode, reproduced
   under controlled conditions.
2. **A metric-naming defect exists in the frozen methodology.**
   `docs/benchmarks/swe-ci.md` names the official metric ANC. The SWE-CI paper's
   metric is EvoScore, a future-weighted mean; ANC is its special case at
   `gamma = 1`, the one setting that discards the maintainability weighting the
   paper exists to introduce. A V10 "ANC" figure may not be placed beside a
   published EvoScore. The page is frozen, so correcting it requires a new
   experiment version. Carried as DEEPER_EVAL M3.
3. **Two prior beliefs were falsified during the epic**, and both are worth
   keeping visible: before T00.5 a C0-versus-C1 comparison would have compared C0
   against itself, and two episodes labelled harmful-memory traps were not traps
   because a no-op would have passed their visible tests.
4. **`negative_transfer` is currently a V10-local term.** The continual-learning
   literature was not surveyed, so the phrase should be used only with its
   operational definition attached. DEEPER_EVAL L1.
5. **The dual freeze admits an unexecutable state.** The platform freeze forbids
   adding an evaluation dispatch path; the experiment freeze forbids adding a
   gate to a sealed manifest. T07 hit exactly that corner and recorded the
   blocker rather than working around it, which was correct and which also means
   the rules as written need a documented escape hatch: a new experiment version.

## Human prerequisites, in priority order

1. **`MATERIALIZE_LICENSED_CORPORA`** — unlocks H1a, H1b, H1c and the external
   half of H2. Per benchmark: recorded approval, materialization evidence
   enumerating task identifiers, a registry edit, and a freeze amendment. Does
   not permit re-drawing any split.
2. **`EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS`** — cheapest path
   from zero decided hypotheses to one, because that corpus is already
   materialized and proved to discriminate. Requires a **new experiment
   version**, not an amendment.
3. **`FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE`** plus provider credentials and
   `MAINTENANCE_EVALS_FRONTIER_SPEND_CAP_USD` — unlocks H2. A recorded decision
   to drop H2 is an equally valid resolution and is preferable to leaving the
   gate open.
4. **One live C1 run against the real 2070 endpoint**, with `controller_provider`
   and `controller_data_left_homelab` checked, before any C1 batch is scored.
5. **Decide H1 on dev, then re-freeze the strategy D/E/H inherit.** If the winner
   is not `local-recursive-fallback`, the inheriting arms must be re-run.

## Verification

Documentation-only ticket. No Python changed, so `pytest` and `ruff` were not
re-run; the last recorded state is 178 passed at T09, with `ruff` outstanding for
T08/T09 (DEEPER_EVAL H2).

What was verified instead:

- Every digest quoted in `V10_RESULTS.md` was read from a frozen `freeze.json` or
  `batch-freeze.json`, not transcribed from a handoff.
- Every literature figure was checked against the paper's abstract or body and is
  attributed to the section it came from. Where the frozen V10 methodology and
  the paper disagree (ANC versus EvoScore), the discrepancy is reported rather
  than reconciled silently.
- No result file, freeze file, manifest, or corpus was modified. `git status` on
  `maintenance-evals` should show only added or modified Markdown.

## Deployment

Deploy verification is **N/A**. T10 changed only documentation in
`maintenance-evals` and `agent-control-plane`. No ACP runtime code, model
routing, dispatch policy, worker image, credential, CT103 behaviour, or CT104
behaviour changed. The platform freeze remains `eval-baseline-2026-08` at
`2532de7cf5098baa461e49b92e0d338c089cff45`.

## Open follow-ups

- The coordinator must commit the `maintenance-evals` documentation set and the
  ACP documentation tree, and replace the remaining "coordinator commit pending"
  tips in handoffs 037, 038, 043, 044, and the ledger (DEEPER_EVAL H1).
- Epic definition-of-done items 8 through 16 remain unmet. Item 17 is met: the
  three required reports are written. Item 18 is deferred to the human gates
  above, which is the point — the next epic must be chosen on evidence, and the
  evidence does not exist yet.
- No further V10 ticket can be assigned to an agent. The remaining work is human
  decisions about licences, money, and platform scope.
