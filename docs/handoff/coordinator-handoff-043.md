# Handoff — coordinator-handoff-043

## Meta

| Field | Value |
|---|---|
| Handoff ID | 043 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T08 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` (unchanged, not amended) |
| ACP change | Documentation only |
| Status | WaitingHuman (harness scaffolding); not Done |
| `stopped_reason` | `ticket_waiting_human_frontier_identity_credentials_spend_cap` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-043.md
ticket: T08
status: WaitingHuman (harness scaffolding complete; paid execution blocked)
experiment_freeze: v10-experiment-freeze-2026-08-16
experiment_id: v10-frontier-hybrid
experiment_version: 1.1.0-t04-frozen
arms: frontier-direct (F), frontier-same-harness (G)
execution_order: seeded_block_randomized
execution_order_seed: 20260815
execution_blocks: benchmark,task_id,repeat_index
result_path: maintenance-evals/results/v10-t08-frontier-fg-synthetic-harness-v1
batch_sha256: fdd821bfc5f4efd48cd35bdecd5fba92c8bbfc71516fa8e3c14d99723970efda
swe_ci_result_set_sha256: 37deeb82ccd3d6d472960036608f143782e9f46eaade55cb86896e2f030e8d0f
swe_chain_result_set_sha256: ab2768bd81bed924e384b29d2f4a80a993be3a781ff23f0bce7b44be0c6ae723
result_scope: scored=false; corpus=synthetic_harness; agent_execution=false; no paid calls
official_swe_ci_success_rate: null
official_swe_chain_success_rate: null
official_benchmark_claim: none
open_blockers: FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE
paid_execution_blockers_when_frontier_id_set: MISSING_PROVIDER_CREDENTIALS, MISSING_SPEND_CAP
frontier_model_id: null
tests: 169 passed
ruff: not run (local pip SSL blocked; code follows existing suite patterns)
deploy_verify: N/A (evaluation harness + documentation only; no ACP runtime change)
blocker: FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE; provider credentials; spend cap
next_ticket_id: T09
t09_note: T09 depends on T08; orchestrator decides whether T09 scaffolding proceeds under WaitingHuman or waits for T08 Done
stopped_reason: ticket_waiting_human_frontier_identity_credentials_spend_cap
```

## Implemented

- `src/maintenance_evals/frontier_spend.py` — fail-closed spend-cap and
  credential gates. Refuses paid provider calls when `frontier_id` is null,
  credentials are absent, or the total spend cap env var is unset. Never logs
  secret values.
- `suites/frontier_hybrid.py` — frozen F/G scheduling on the same SWE-CI and
  SWE-Chain validation task subsets as T06, separate benchmark freezes,
  frontier-specific telemetry validation, and documented F limitations versus G
  same-harness verifier path.
- `scripts/run_frontier_hybrid_harness.py` — synthetic harness driver that
  emits configuration-only records without invoking a frontier provider.
- `tests/test_frontier_hybrid.py` — scheduling, freeze, gate refusal, and
  spend-cap enforcement tests.
- `docs/FRONTIER_CREDENTIALS.md` — human prerequisites for provider identity,
  credentials, and spend cap.

## Frozen synthetic harness result

24 slots total (2 benchmarks x 2 synthetic tasks x 2 F/G arms x 3 repeats).
Every record states `agent_execution=false`, `frontier_invoked=false`, and
keeps all outcome and paid-usage fields null. Batch and per-benchmark freezes
record `open_blockers: [FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE]`.

## Not executed

No paid frontier provider calls were made. No frontier model identity or price
was invented. Official SWE-CI/SWE-Chain frontier outcomes remain unclaimed.

## Human prerequisites to reach Done

1. Clear `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE`: select provider and model,
   add a cited price row under a new pricing version, set `frontier_id` in
   `v10-frontier-hybrid.yaml`, amend `v10-experiment-freeze.md`.
2. Configure operator secrets per `docs/FRONTIER_CREDENTIALS.md`.
3. Set `MAINTENANCE_EVALS_FRONTIER_SPEND_CAP_USD`.
4. Clear `MATERIALIZE_LICENSED_CORPORA` before official scored frontier runs.

## T09 dependency

Epic deps require T09 to follow T08. T08 is **WaitingHuman**, not Done.
Orchestrator should decide whether T09 hybrid scaffolding may proceed under its
own WaitingHuman gates or should wait until T08 clears frontier identity.

## Verification

- `PYTHONPATH=src py -3.11 -m pytest tests/ -q` — 169 passed.
- `PYTHONPATH=src:. py -3.11 scripts/run_frontier_hybrid_harness.py` — emitted
  batch `fdd821bf…`.
