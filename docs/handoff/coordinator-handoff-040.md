# Handoff — coordinator-handoff-040

## Meta

| Field | Value |
|---|---|
| Handoff ID | 040 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T05 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` at `b282f6d` |
| ACP change | Documentation only |
| Status | Done (harness + result-freeze path); WaitingHuman (official ARB/SWE-CI H1) |
| `stopped_reason` | `ticket_done_harness_official_waiting_human` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-040.md
ticket: T05
status: Done (harness + freeze path); WaitingHuman (official ARB/SWE-CI H1)
experiment_freeze: v10-experiment-freeze-2026-08-16
execution_order: seeded_block_randomized
execution_order_seed: 20260815
result_path: maintenance-evals/results/v10-t05-context-ablation-synthetic-harness-v1
result_set_sha256: 836086c8bf7b71bae0b403b6d5ab2ac0a155484ca5349b1996c4fa41cc7b3980
result_scope: scored=false; corpus=synthetic_harness; agent_execution=false
official_h1_claim: none
tests: 124 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation harness + documentation only)
blocker: MATERIALIZE_LICENSED_CORPORA
next_ticket_id: T06
stopped_reason: ticket_done_harness_official_waiting_human
```

## Implemented

- Replaced `suites/context_ablation.py` with the frozen A/B/C0/C1 batch
  orchestrator. It requires exactly `local-direct`, `local-deterministic`,
  `local-recursive-fallback`, and `local-recursive-2070`.
- Bound execution to seeded block randomization using seed `20260815` and
  blocks `[task_id, repeat_index]`. Input order cannot alter the resulting
  schedule.
- Added fail-closed scope checks. The frozen context-ablation manifest cannot
  run scored while `scored_runs_allowed` is false; synthetic harness output
  must declare `corpus=synthetic_harness` and `scored=false`.
- Added telemetry truth checks: C0 rejects any model-controller invocation;
  triggered C1 requires both `controller_model_invoked=true` and a resolved
  `controller_model_id`.
- Added create-only result freezing with separate hashes for execution order
  and raw JSONL results, plus a combined result-set SHA-256. Existing result
  directories cannot be overwritten.
- The batch runner executes each committed slot once. It does not retry,
  repair, tune, or rewrite an evaluated-agent result.

## Frozen synthetic harness result

The reproducible smoke script
`scripts/run_context_ablation_harness.py` emitted 24 slots: two synthetic
configuration tasks, four arms, and three repeats. It exercises arm binding,
ordering, and the result-freeze path only.

The raw records deliberately state:

```text
scored=false
corpus=synthetic_harness
agent_execution=false
official_benchmark_pass=null
v10_additional_verification_pass=null
verified_success=null
claim_scope=harness_only_no_official_h1_claim
```

The synthetic record does not claim that C1 called the live 2070 controller.
Live invocation truth remains an execution-time requirement for a licensed
official batch.

## Verification

- `py -3.11 -m pytest -q` with project source path — 124 passed.
- `python -m ruff check .` — All checks passed.
- IDE diagnostics on the three implementation/test files — no errors.
- Result-set SHA-256:
  `836086c8bf7b71bae0b403b6d5ab2ac0a155484ca5349b1996c4fa41cc7b3980`.

## Official result status

No official ARB or SWE-CI corpus was downloaded or scored. No H1a/H1b/H1c
metric or winner is claimed. Official T05 execution remains WaitingHuman on
`MATERIALIZE_LICENSED_CORPORA`, exactly as sealed by T04.

T06 is next in the strict spine. Its official SWE-CI/SWE-Chain execution is
also WaitingHuman on the same licence/materialization gate; that gate must not
be bypassed or represented as a benchmark result.
