# Boss ledger V7 preview — Recursive Context Evaluation and Controller Bake-off

**Status:** superseded — epic **opened** 2026-07-21. Active ledger: **[boss-ledger-v7.md](boss-ledger-v7.md)**.

| Field | Value |
|-------|-------|
| **Epic name** | V7 — Recursive context evaluation and controller bake-off |
| **Prior epic** | [boss-ledger-v6.md](boss-ledger-v6.md) |
| **Origin** | Deferred V4 T12 + V6 eval export foundation |
| **Epic status** | in progress (see active ledger) |

## Inputs from V6

- Content-addressed `eval_bundle.v1` via `agentctl eval export --run-id …`
- Agent Observatory + observation projection shared with `agentctl trace show`
- Separate authorization predicates; shadow injection assessments; `@agent` NL FSM

## Planned scope (moved to active ledger)

1. Import V6 bundles into **Inspect AI** harness (framework-neutral → Inspect adapters).
2. Profiles **A–D** (controller / context strategy ablation).
3. Metrics: CT102 verified success, repair iterations, fallback frequency, policy violations, tokens/cost/time.
4. Memory isolation: fork/reset namespaces between profiles using export `memory_namespace` metadata.

## Explicit non-goals

- Do not enable unbounded recursive controllers in production.
- Do not treat LlamaFirewall shadow results as authority.
- Do not mutate production memory during bake-off imports.
