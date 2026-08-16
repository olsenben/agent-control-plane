# Handoff — coordinator-handoff-044

## Meta

| Field | Value |
|---|---|
| Handoff ID | 044 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T09 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Experiment freeze | `v10-experiment-freeze-2026-08-16` (unchanged, not amended) |
| ACP change | Documentation only (`boss-ledger-v10.md`, this handoff) |
| Status | WaitingHuman (harness scaffolding); not Done |
| `stopped_reason` | `ticket_waiting_human_frontier_identity_credentials_spend_cap_and_licensed_corpora` |

## Sealed return

```text
handoff_path: docs/handoff/coordinator-handoff-044.md
ticket: T09
status: WaitingHuman (harness scaffolding complete; scored hybrid + held-out blocked)
experiment_freeze: v10-experiment-freeze-2026-08-16
experiment_id: v10-hybrid-held-out
experiment_version: 1.1.0-t04-frozen
arm: hybrid
frozen_local_strategy: local-recursive-fallback
frozen_local_strategy_label: PROVISIONAL_NOT_FOR_H2
frozen_controller_backend: deterministic
route: preflight -> local_qwen_direct -> conditional_recursive -> local_qwen_repair -> verification -> typed_frontier_escalation
typed_escalation_triggers: attempt_budget_exhausted, contradictory_evidence_unresolved, context_overflow_unresolved, cross_repo_ambiguity_threshold, verification_failure_fingerprint, policy_approved_escalation_class
held_out_split: test
held_out_public_benchmarks: SWE-CI, SWE-Chain, Agent-Retrieval-Bench
longitudinal_held_out_repositories: synthlab/config-loader, synthlab/text-normalizer (reserved since T07; executes under v10-longitudinal when gates clear)
execution_order: seeded_block_randomized
execution_order_seed: 20260815
execution_blocks: benchmark,task_id,repeat_index
result_path: maintenance-evals/results/v10-t09-hybrid-h-held-out-synthetic-harness-v1
batch_sha256: e3eba0ed6b007952c3f58226743ad828f8db0cb4579c2f96000030f9828b9d24
swe_ci_result_set_sha256: 30e272da90c45fa771bc12253fdeea9c410e53aa25af8d7aca1d78902e5786d0
swe_chain_result_set_sha256: 5a8563c6b6ea03029a59dfb3523fa50ad2f21d90fa870d213ca8dde69e85f2a0
arb_result_set_sha256: ba38cd7115918b458fdb6ed5b8e8b03785a67bd18f27aa28b1a6e71504f8dd43
result_scope: scored=false; corpus=synthetic_harness; agent_execution=false; no paid calls; held_out_not_inspected
official_h2_claim: none
open_blockers: FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE, MATERIALIZE_LICENSED_CORPORA
paid_execution_blockers_when_frontier_id_set: MISSING_PROVIDER_CREDENTIALS, MISSING_SPEND_CAP
frontier_model_id: null
tests: 178 passed
ruff: not run (local pip SSL blocked; code follows existing suite patterns)
deploy_verify: N/A (evaluation harness + documentation only; no ACP runtime change)
blocker: FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE; MATERIALIZE_LICENSED_CORPORA; provider credentials; spend cap
next_ticket_id: T10
t10_note: T10 frozen analysis may proceed on partial evidence from T05-T09 harness freezes; no official H2 or held-out outcome claims
stopped_reason: ticket_waiting_human_frontier_identity_credentials_spend_cap_and_licensed_corpora
```

## Implemented

- `src/maintenance_evals/hybrid_route.py` — pre-registered route stub with six
  typed escalation triggers; refuses paid escalation without credentials via
  `frontier_spend` hooks.
- `src/maintenance_evals/held_out.py` — held-out split guards and reservation
  summary; documents `synthlab/config-loader` and `synthlab/text-normalizer`
  reserved since T07.
- `suites/hybrid_h.py` — frozen hybrid arm H scheduling on public held-out
  benchmarks, separate benchmark freezes, route telemetry validation.
- `manifests/experiments/v10-hybrid-held-out.yaml` — frozen experiment manifest
  (public held-out only; longitudinal test repos documented separately).
- `scripts/run_hybrid_h_harness.py` — synthetic harness driver emitting
  configuration-only records without agent or paid execution.
- `tests/test_hybrid_h.py` — route, gate refusal, held-out guard, and freeze tests.
- `docs/HYBRID_H_HELD_OUT.md` — route, gates, and held-out reservation docs.

## Frozen synthetic harness result

15 slots total (SWE-CI 6 + SWE-Chain 6 + Agent-Retrieval-Bench 3). Every record
states `agent_execution=false`, `frontier_invoked=false`,
`frontier_escalation_blocked=true`, and keeps all outcome and paid-usage fields
null. Batch records `open_blockers`:
`[FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE]` plus manifest gate
`MATERIALIZE_LICENSED_CORPORA` for official public held-out runs.

## Not executed

No paid frontier provider calls. No official scored hybrid or held-out batches.
Longitudinal test repositories remain unread. T08 remains WaitingHuman; T09 does
not depend on T08 Done for scaffolding but cannot claim scored H2 until T08
gates clear.

## Human prerequisites to reach Done

1. Clear `FREEZE_FRONTIER_MODEL_IDENTITY_AND_PRICE` (same checklist as T08).
2. Configure operator secrets per `docs/FRONTIER_CREDENTIALS.md`.
3. Set `MAINTENANCE_EVALS_FRONTIER_SPEND_CAP_USD`.
4. Clear `MATERIALIZE_LICENSED_CORPORA` before official public held-out runs.
5. Execute held-out replication on untouched test splits without post-hoc tuning.

## T10 dependency

T10 analysis may proceed on frozen partial evidence from T05–T09 harness
freezes. No official H2 or held-out outcome claims are available until human
gates clear.

## Verification

- `PYTHONPATH=src py -3.11 -m pytest tests/ -q` — 178 passed.
- `PYTHONPATH=src:. py -3.11 scripts/run_hybrid_h_harness.py` — emitted batch
  `e3eba0ed…`.
