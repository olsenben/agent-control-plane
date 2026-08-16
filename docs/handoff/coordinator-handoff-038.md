# Handoff — coordinator-handoff-038

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 038 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T03 |
| Evaluation repo | `ai-sdlc-lab/maintenance-evals` |
| Evaluation repo tip | Coordinator commit pending; baseline `e9269e4` plus uncommitted T02/T03 working tree |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `ticket_done` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-038.md
ticket: T03
status: Done
repo: ai-sdlc-lab/maintenance-evals
tip: coordinator commit pending (baseline e9269e4 plus T02/T03 working tree)
tests: 16 passed
ruff: All checks passed!
deploy_verify: N/A (evaluation-only telemetry/accounting; no ACP behavior changed)
blocker: none
next_ticket_id: T04
stopped_reason: ticket_done
```

## Slice outcome

- Added deterministic normalization from terminal `evaluation_telemetry` and
  trajectory-like artifacts. Session summaries take precedence; missing summary
  values are filled from artifact aggregation without double-counting.
- Normalized primary/local, recursive-controller, and frontier token usage;
  local/controller GPU seconds; recursive trigger count/reasons, subcalls,
  maximum depth, and query count; wall time; solver/repair attempts; and CI
  cycles.
- Removed zero-filling for unknown usage, attempts, CI cycles, recursive
  counters, and invocation state. Results preserve `null`, a sorted
  `missing_fields` list, and per-metric source provenance.
- Kept deterministic fallback distinct from live model-controller invocation
  through nullable `controller_model_invoked` plus the existing
  `controller_backend`.
- Replaced the T01 pricing placeholder with versioned
  `pricing/pricing-2026-08.yaml`. The pre-freeze table intentionally contains no
  frontier row because provider/model identity remains `RESOLVE_IN_T04`.
- Added a strict price-table loader and Decimal calculator. Prices exist only in
  YAML, rates must be quoted decimal strings, cached input cannot exceed prompt
  input, and each result records pricing version and exact table SHA-256.
- Added explicit `calculated`, `no_paid_api_usage`, `unknown_usage`, and
  `unknown_price` cost statuses. Unknown usage or price always yields a null
  paid-dollar claim; zero dollars is emitted only when an artifact explicitly
  records that paid frontier invocation did not occur.
- Kept provider-reported frontier cost, deterministically recomputed paid API
  dollars, local/controller GPU seconds, and wall time as separate fields.
- Added `docs/COST_ACCOUNTING.md`, schema/fixture updates, and focused
  normalization, deterministic pricing, malformed pricing, and fail-closed
  tests.

## Decisions the next coordinator must honor

1. T04 must add the selected frontier provider/model and cited effective rates
   to a versioned price table before any paid scored run. Do not rewrite a table
   after results reference its SHA.
2. Never coerce null usage, attempt counts, CI cycles, invocation state, or cost
   claims to zero in adapters or analysis.
3. A `no_paid_api_usage` zero is valid only when `frontier_invoked` is
   explicitly false. Unknown invocation is `unknown_usage`.
4. Keep `frontier_cost_usd` (provider reported) distinct from
   `paid_api_cost_usd` (recomputed), and keep both distinct from local/controller
   GPU seconds.
5. Terminal session summaries are authoritative rollups. Use trajectory records
   only for missing metrics; never add both representations of the same metric.
6. T04 owns benchmark adapters, metadata, split identities, frontier identity,
   frontier pricing freeze, and experiment freeze. T03 did not alter ACP model
   routing, dispatch policy, or agent behavior.

## Verification performed

- `$env:PYTHONPATH='src'; py -3.11 -m pytest` — 16 passed.
- `python -m ruff check .` — All checks passed.
- IDE diagnostics on edited Python files — no linter errors.
- `git diff --check` — no whitespace errors.
- Tests cover summary precedence, artifact aggregation, local/controller/frontier
  separation, recursive telemetry, measured wall time, explicit unknowns,
  deterministic Decimal cost, unknown usage/price, explicit no-paid-use zero,
  and rejection of unquoted YAML float rates.

## Deployment

Deploy verification is **N/A**. T03 changes only the evaluation package,
contracts, pricing data, and documentation. No `agent-control-plane` runtime
code, model routing, worker image, credentials, CT103 behavior, or CT104 behavior
changed.

## Open follow-ups

- Coordinator must commit the accumulated T02/T03 `maintenance-evals` working
  tree and replace the pending tip in handoffs 037/038 and the boss ledger.
- T04 must freeze the selected frontier provider/model pricing row before paid
  scored execution.
- T04 must complete benchmark adapters/metadata, frozen split identities, and
  `docs/handoff/v10-experiment-freeze.md` before T05.
