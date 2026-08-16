# Handoff — coordinator-handoff-037

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 037 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T02 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Evaluation repo tip | Coordinator commit pending; baseline `e9269e4` |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `ticket_done` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-037.md
ticket: T02
status: Done
repo: ai-sdlc-lab/maintenance-evals
tip: coordinator commit pending (baseline e9269e4)
tests: 11 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation-only package; trusted dispatch interface fixture-tested)
blocker: none
next_ticket_id: T03
stopped_reason: ticket_done
```

## Slice outcome

- Added an exact-SHA runner that allocates `eval-<uuid>` identities, creates a
  fresh non-reused Git checkout, detaches at the task's exact 40-character SHA,
  verifies `HEAD`, and rejects identity or manifest-hash drift on validation.
- Added create-only `request.json`, `dispatch.json`, and `result.json` audit
  records. Replay allocates a new run and never rewrites or deletes prior audit
  history.
- Added a mockable `ControlPlaneClient` boundary and JSON-command production
  adapter. The adapter submits `maintenance_eval_dispatch.v1` through a
  deployment-provided trusted control-plane command, polls the canonical
  terminal `AgentSession`, and collects result SHA, verification claim, and
  optional evaluation telemetry.
- Arm configuration carries context strategy, `controller_backend`, frontier
  policy, and memory policy. Reset/off use isolated run namespaces;
  `preserve_verified` uses a scoped verified-memory namespace. Every dispatch
  explicitly retains audit history.
- Infrastructure reason codes and transport/timeouts are classified separately
  from evaluated-agent failures; harness failures remain a third class.
- Extended `maintenance_eval_result.v1` with required `eval_run_id` and nullable
  exact `result_sha`, closing the T01 provenance gap.
- Added `evalctl run`, `evalctl replay`, and `evalctl validate-run`.
- Added an input-order-independent `seeded_block_randomized` helper that derives
  a deterministic seed per declared block.
- Added synthetic client/workspace fixtures and local-Git exact-SHA tests. No
  live GPU, provider, CT103, or CT104 dependency is required.

## Decisions the next coordinator must honor

1. T03 adds usage/cost telemetry and pricing only; do not place provider pricing
   logic in the T02 runner.
2. The JSON command adapter is a transport boundary, not an alternate agent
   implementation. Its deployment command must enter the existing trusted
   control-plane path and return canonical AgentSession/verification data.
3. A memory reset means selecting a fresh namespace. Never delete memory or
   prior request/result records.
4. Infrastructure-failed slots remain excluded and rerun without consuming the
   repeat, as frozen in the experiment manifests.
5. `official_benchmark_pass` and
   `v10_additional_verification_pass` remain separate.
6. No public benchmark adapter work belongs to T03; adapters and experiment
   freeze remain T04.

## Verification performed

- `PYTHONPATH=src py -3.11 -m pytest` — 11 passed
- `python -m ruff check .` — All checks passed
- Tests cover exact SHA checkout, immutable IDs/create-only records, fresh
  replay identity, original-audit preservation, terminal polling, result SHA
  and verification claims, infrastructure classification, deterministic block
  randomization, CLI validation, and tamper detection.

## Deployment

Deploy verification is **N/A**. T02 changes the evaluation-only package and adds
an injectable boundary to the existing control plane; it does not modify
CT103/CT104 runtime code, images, credentials, or model configuration. A live
adapter smoke belongs with the first authorized harness execution after its
deployment command is configured.

## Open follow-ups

- Coordinator must commit the `maintenance-evals` changes and replace the
  pending tip in this handoff and the boss ledger with the resulting SHA.
- T03 adds cost/usage telemetry and frozen pricing provenance.
- T04 resolves benchmark adapters/metadata, split identities, frontier model,
  and creates the experiment freeze before any scored run.
