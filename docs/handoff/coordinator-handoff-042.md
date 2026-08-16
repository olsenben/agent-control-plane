# Handoff — coordinator-handoff-042

## Meta

| Field | Value |
|---|---|
| Handoff ID | 042 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T07 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` at `002fdc0` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` (unchanged, not amended) |
| ACP change | Documentation only |
| Status | Done (D/E harness + real execution + frozen result set); H3 unclaimed pending agent execution |
| `stopped_reason` | `ticket_done_h3_instrument_verified_agent_execution_blocked` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-042.md
ticket: T07
status: Done (harness + real corpus execution + frozen result set); H3 unclaimed
experiment_freeze: v10-experiment-freeze-2026-08-16
experiment_id: v10-longitudinal
experiment_version: 1.1.0-t04-frozen
arms: local-recursive-memory-reset (D), local-recursive-memory (E)
frozen_local_strategy: local-recursive-fallback
frozen_local_strategy_label: PROVISIONAL_NOT_FOR_H2
execution_order: seeded_block_randomized
execution_order_seed: 20260815
execution_blocks: repository_sequence,episode_index,repeat_index
splits_executed: dev,validation
splits_reserved: test (config-loader, text-normalizer) untouched for T09
result_path: maintenance-evals/results/v10-t07-longitudinal-de-v1
result_set_sha256: 6f2fe30804e49be15c36e0d4070aeb4da6cbf51934ae2b457458a3cc0684fcc8
replay_invariant_sha256: 4a1e3c979ffe100934172de635717e17f56093356f5a3bae8c20ab691bf714dd
execution_order_sha256: 503b0a7bbf8e64d0c0001939af1c7a0658353bcc4506ccee277c641ce4e83ec6
audit_ledger_sha256: ffdc21236f567bd2e368d90139d2f9d3c7a353438c97d25dfcc51e90860def32
memory_events_sha256: 13fa6b8c68014ad77ba81a155b43e51f7c6d7d814f5f87a0772c39f7e75ec058
verifier_instrument_sha256: 41db76855d66df424c51e73d04006dde8fb0b4f21340d51d07be7bbf205a8f34
result_scope: scored=false; corpus=synthetic_longitudinal_frozen_corpus; agent_execution=false
slots: 108 (18 episodes x 2 arms x 3 repeats)
eligible_records_per_arm: 135
retrieved_records_D: 0
retrieved_records_E: 135
suppressed_records_D: 135
future_commits_reachable: 0 in 108/108
future_evidence_retrievals: 0
audit_chain_verified: true
audit_history_retained_runs: 108/108
stale_retrievals: 42 (18 invalidated, 18 contradicted, 6 superseded)
helpful_retrievals: 0
harmful_retrievals: null (no agent verdict)
negative_transfer_rate: null (not zero)
negative_transfer_detectable: 3/3 trap episodes (dev 1, validation 2)
reference_resolutions_accepted: 18/18
h3_claimed: false
h3_verdict: unclaimed
official_swe_chain_success_rate: null
official_swe_ci_success_rate: null
official_benchmark_claim: none
tests: 163 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation repo + documentation only; no ACP runtime change)
blocker: EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS
next_ticket_id: T08
stopped_reason: ticket_done_h3_instrument_verified_agent_execution_blocked
```

## Implemented

- `src/maintenance_evals/memory.py` — content-addressed reusable-memory store.
  Admission requires machine-recorded dual verification and rejects a claim
  carrying the resolution SHA or a hidden-check path rather than sanitizing it.
  A hash-chained append-only audit ledger is written by both arms, so the reset
  arm discards retrievability without discarding reproducibility. Eligibility is
  a strict inequality on episode index within a repository and on admission
  sequence across repositories. Validity transitions are split by phase:
  `stale_memory` and `contradictory_memory` age a record before the consuming
  episode runs, `superseded_memory` after that episode verifies.
- `src/maintenance_evals/verification.py` — really executes the frozen official
  and V10-additional command lists, keeps the two verdicts separate, and derives
  a verification claim id from the executed commands, workspace commit and exit
  statuses, so a claim cannot be cited for evidence that was not produced.
- `suites/longitudinal.py` — frozen D/E scheduling and freezing. Refuses a batch
  whose arms differ in anything but memory policy, whose reset arm consumed
  prior-episode memory, whose retrieval lacks an effect label, whose workspace
  can reach a commit past its starting commit, or that claims H3 while unscored.
  Interleaves the two arms inside each `(repository, episode, repeat)` block
  while asserting each lineage still advances through episodes in causal order.
- `scripts/run_longitudinal_de.py` — the real execution driver.
- `analysis/longitudinal.py`, `analysis/negative_transfer.py`,
  `scripts/analyze_longitudinal_de.py` — analysis that reads only the frozen
  result-set directory and re-verifies every recorded digest before reading a
  row.
- `docs/analysis/v10-t07-longitudinal-de.md` — the narrative analysis, written
  after the seal, from the frozen files only.

## Executed for real

108 slots over the 18 executable episodes: `synthlab/retry-toolkit` (dev, 6) and
`synthlab/ledger-core` + `synthlab/ledger-api` (validation, 12), three repeats
in each arm. Every slot cloned the episode's own bare snapshot at its exact
starting commit and ran the frozen official and V10-additional verifier commands
against the unrepaired workspace. Two verifier-only probes ran per episode: the
reference resolution and, for trap episodes, the misapplied-memory variant.

Measured rather than asserted:

```text
both arms saw the same 135 eligible records; D consumed 0, E consumed 135
future_commits_reachable = 0 in all 108 records
future_evidence_retrievals = 0
audit chain recomputes; 108/108 records retain audit history
arms_share_starting_commits = true; unrepaired workspace failed both checks 108/108
42 of 135 retrievals stale from recorded validity transitions, all returned not filtered
18/18 reference resolutions accepted by both check families
3/3 trap variants pass the official check and fail the frozen additional checks
```

The test split was not cloned, verified or read. The driver fails closed if a
test-split episode enters the batch.

## H3 is unclaimed, not null

No slot reached the frozen platform's patch-authoring agent, so
`agent_execution` is false in all 108 records and `official_benchmark_pass`,
`v10_additional_verification_pass`, `verified_success` and `solver_attempts` are
null. No D-versus-E attempt, cost, latency or success comparison exists in this
result set and none may be quoted from it.

The reason is a platform boundary. The episodes are local bare Git snapshots,
the frozen control plane exposes no evaluation dispatch path to them, and
`adapters/agent_control.py` is still a boundary placeholder. Building that path
would change the platform frozen at `2532de7`, which G9 forbids after T04. The
frozen manifest is sealed and could not gain a new `resolve_before_scoring`
gate without opening a new experiment version, so the blocker
`EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS` is recorded on the
result-set freeze and in the analysis instead.

Harmful and negative-transfer rates are null rather than zero, and the frozen
five-percent H3 threshold is recorded as `threshold_evaluable: false` against a
real denominator of 45 memory-using runs. Reporting zero would have been the
more flattering number and the false one.

What T07 does establish is that the H3 instrument works: the arms are separated
on exactly one variable, future evidence cannot flow backward, staleness
semantics fire on real data, and negative transfer is detectable in the
validation split rather than only defined. If the official verifier alone were
used, a misapplied memory would score as a success in all three trap episodes.

## Discipline

- Result set created write-once and sealed before the analysis was written.
- No agent, prompt, strategy or threshold changed during or after the batch.
- `local-recursive-fallback` carried forward as the frozen local strategy for
  this experiment version, labelled `PROVISIONAL_NOT_FOR_H2` in the freeze and
  in every record. Not an empirical winner.
- No official SWE-Chain, SWE-CI or Agent-Retrieval-Bench score is computed,
  implied or claimed. The secondary SWE-Chain D/E analysis is deferred with
  `MATERIALIZE_LICENSED_CORPORA`.
- Replay reproduces `execution-order.json`, `audit-ledger.jsonl` and
  `memory-events.jsonl` byte for byte, and reproduces
  `replay_invariant_sha256`, which excludes only measured durations, run-scoped
  workspace paths and captured output embedding both.

## Verification

- `py -3.11 -m pytest` with project source path — 163 passed.
- `python -m ruff check .` — All checks passed.
- IDE diagnostics on memory, verification, suite, driver and analysis modules —
  no errors.
- Independent replay of the full batch — `replay_invariant_sha256` matched.

## Open for T08

T08 (frontier F/G) does not depend on an H3 verdict, so the spine is not
blocked. The H3 row of the T10 go/no-go report is currently an open gate rather
than a finding, and T09 inherits an instrument that has been verified but not yet
used to score an agent.
