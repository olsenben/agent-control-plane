# Handoff — coordinator-handoff-041

## Meta

| Field | Value |
|---|---|
| Handoff ID | 041 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T06 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` at `b282f6d` |
| ACP change | Documentation only |
| Status | Done (harness + separate freezes); WaitingHuman (official SWE-CI/SWE-Chain) |
| `stopped_reason` | `ticket_done_harness_official_waiting_human` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-041.md
ticket: T06
status: Done (harness + separate freezes); WaitingHuman (official SWE-CI/SWE-Chain)
experiment_freeze: v10-experiment-freeze-2026-08-16
execution_order: seeded_block_randomized
execution_order_seed: 20260815
execution_blocks: benchmark,task_id,repeat_index
result_path: maintenance-evals/results/v10-t06-maintenance-end-to-end-synthetic-harness-v1
batch_sha256: 1750165e89b6e4a63f0d796831c72c3bc1364cfcee4cdbece4e286eb10333c6e
swe_ci_result_set_sha256: dd4a786c6dfb3b03082ed661414b87df8e17c6366884a4cc57cf6b22d33126d9
swe_chain_result_set_sha256: 7ed3a677d131827f375a61dae46e4603ef4dd2b6f657faa6992b0f7cd0389afa
result_scope: scored=false; corpus=synthetic_harness; agent_execution=false
official_swe_ci_success_rate: null
official_swe_chain_success_rate: null
official_benchmark_claim: none
provisional_best_local_strategy: local-recursive-fallback
provisional_label: PROVISIONAL_NOT_FOR_H2
h2_eligible: false
tests: 128 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation harness + documentation only)
blocker: MATERIALIZE_LICENSED_CORPORA
next_ticket_id: T07
stopped_reason: ticket_done_harness_official_waiting_human
```

## Implemented

- Replaced the T01 placeholder with the frozen T06 local-maintenance
  orchestrator for `local-direct`, `local-deterministic`,
  `local-recursive-fallback`, and `local-recursive-2070`.
- Bound execution to seed `20260815` and blocks
  `[benchmark, task_id, repeat_index]`. Input task order cannot change a
  block's arm order.
- Added fail-closed scope checks. The frozen T06 manifest cannot run scored
  while `scored_runs_allowed` is false; the harness path requires
  `corpus=synthetic_harness` and `scored=false`.
- Required benchmark-specific end-to-end telemetry for CI outcomes, attempts,
  cycles, context, controller truth, latency, GPU time, and failure class.
  Configuration-only records must keep all outcome fields null.
- Rejected any record indicating hidden benchmark artifacts entered model
  context. Preserved distinct `harness`, `infrastructure`, and
  `evaluated_agent` failure classes.
- Kept C0/C1 truth auditable: C0 cannot report a model-controller call, and a
  triggered C1 must identify the invoked model controller.
- Added create-only benchmark-specific execution orders, raw JSONL records,
  and freeze files, plus a batch index and content hash.

## Frozen synthetic harness result

The reproducible script
`scripts/run_maintenance_end_to_end_harness.py` emitted two independent
24-slot result sets. Each benchmark has two synthetic contract tasks, four
arms, and three repeats.

Both result sets state:

```text
scored=false
corpus=synthetic_harness
agent_execution=false
official_benchmark_pass=null
v10_additional_verification_pass=null
verified_success=null
claim_scope=harness_only_no_official_benchmark_claim
```

SWE-CI and SWE-Chain are not combined into a headline rate. No success rate is
computed or claimed.

## Provisional local strategy

`local-recursive-fallback` is selected for T07 harness continuity on
configuration and operational-determinism grounds only. The selection artifact
records:

```text
label=PROVISIONAL_NOT_FOR_H2
eligible_for_h2=false
official_swe_ci_success_rate=null
official_swe_chain_success_rate=null
superseded_by=licensed frozen T06 benchmark analysis
```

This is not an empirical benchmark winner and cannot support H2.

## Verification

- `py -3.11 -m pytest` with project source path — 128 passed.
- `python -m ruff check .` — All checks passed.
- IDE diagnostics on the implementation, runner, and tests — no errors.
- Batch SHA-256:
  `1750165e89b6e4a63f0d796831c72c3bc1364cfcee4cdbece4e286eb10333c6e`.

## Official result status

No official SWE-CI or SWE-Chain corpus was downloaded or scored. Official T06
execution and success-rate analysis remain WaitingHuman on
`MATERIALIZE_LICENSED_CORPORA`. T07 is next in the strict spine and may consume
only the explicitly provisional strategy for synthetic harness continuity.
