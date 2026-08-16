# Handoff — coordinator-handoff-036

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 036 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T01 |
| Evaluation repo tip | `maintenance-evals@e9269e4` |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `ticket_done` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-036.md
ticket: T01
status: Done
repo: ai-sdlc-lab/maintenance-evals
tip: e9269e4
tests: 4 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation-only package)
blocker: none
next_ticket_id: T02
stopped_reason: ticket_done
```

## Slice outcome

- Created the standalone private/evaluation-only `maintenance-evals` Git
  repository and committed the initial package at `e9269e4`.
- Added JSON Schema and recursively frozen Pydantic contracts for
  `maintenance_eval_task.v1`, `maintenance_eval_result.v1`, and
  `experiment_manifest.v1`.
- Pre-registered the A/B/C0/C1 context ablation, maintenance end-to-end,
  longitudinal D/E, and frontier/hybrid F/G/H experiments.
- Included seeded block-randomized ordering, cache/repeat policies, exact H1a,
  H1b, H1c, H2, and H3 decision thresholds, scored failure classification,
  infrastructure/invalid-run policies, dual official/V10 verification metrics,
  and immutable deterministic manifest hashing.
- Frozen `qwen2.5-coder:14b` at `Q4_K_M` and the configured 2070 controller
  `qwen2.5-coder:3b`. Benchmark versions/splits and frontier model identity are
  explicitly `RESOLVE_IN_T04`; all manifests prohibit scored runs before freeze.
- Added the complete §11 layout, synthetic fixtures, methodology, private
  notice, placeholders for later adapters/suites/analysis, and no runner or
  credentials.

## Decisions the next coordinator must honor

1. T02 must drive the existing trusted `agent-control-plane`; it must not
   reimplement evaluated-agent behavior in this repository.
2. Manifest models are recursively frozen and have no save/rewrite helper.
   Harness fixes retain audit records and never rewrite scored manifests/results.
3. `official_benchmark_pass` and `v10_additional_verification_pass` remain
   separate, with `verifier_adequacy_notes` preserving limitations.
4. Failures are scored only as `harness`, `infrastructure`, or
   `evaluated_agent`. Infrastructure runs are excluded and rerun in the same
   randomized slot without consuming a repeat.
5. No scored execution may occur until T04 resolves every `RESOLVE_IN_T04`
   placeholder and creates the experiment freeze.

## Verification performed

- `py -m pytest` — 4 passed
- `py -m ruff check .` — All checks passed
- Manifest tests validate all four YAML files against JSON Schema and typed
  models, cover H1a/H1b/H1c/H2/H3, verify stable hashes, and prove deep frozen
  models reject mutation without rewriting source files.

## Deployment

Deploy verification is **N/A**. T01 creates an evaluation-only package and makes
no control-plane, CT103, CT104, CT102, or model-host runtime change.

## Open follow-ups

- Private Gitea remote creation/push is left to the orchestrator/human.
- T02 adds exact-SHA replay and `evalctl`; no runner exists yet.
- T03 resolves cost telemetry/pricing; T04 resolves benchmark metadata,
  adapters, splits, frontier identity, and the experiment freeze.
