# Boss ledger — V10 Maintenance Evaluation & Economic Bake-off

Epic supervisor state. Prior: [boss-ledger-v9.md](boss-ledger-v9.md) (complete). Epic: [boss-ledger-v10-maintenance-evaluation-revised.md](../boss-ledger-v10-maintenance-evaluation-revised.md). Plan: `.cursor/plans/v10_eval_bakeoff_30f4388b.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | V10 — Maintenance Evaluation & Economic Bake-off |
| **Baseline tip** | `4376ef4` live-certified; docs/tag SHA `2532de7` (`eval-baseline-2026-08`) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) + V10 plan dual-freeze discipline |
| **Integration branch** | `main` |
| **Epic status** | in_progress |
| **Tickets done** | 2 / 12 |
| **Next ticket** | T01 |
| **Latest handoff** | [035](coordinator-handoff-035.md) |
| **Last boss action** | 2026-08-16 — Wave 4 T00.5 deploy-verify PASS on `e5d91ce`; T01 unblocked |
| **Lanes** | main only |
| **Env** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; `docker compose exec -T … </dev/null` |

## Dual freezes

```text
T00/T00.5 = platform freeze
T04       = experiment freeze (docs/handoff/v10-experiment-freeze.md + tag)
T05+      = scored evaluation (no scored runs before experiment freeze)
```

## Spine (strict sequential)

```text
T00 -> T00.5 -> T01 -> T02 -> T03 -> T04 -> T05 -> T06 -> T07 -> T08 -> T09 -> T10
```

One implementation ticket per wave. No T07∥T08.

## Ticket states

`Ready | Running | Done | WaitingHuman | BlockedTechnical | InvalidExperiment`

## Tickets

| ID | Slice | Deps | Status | Tip |
|----|-------|------|--------|-----|
| **T00** | Platform baseline freeze + stale-doc reconciliation | — | Done | `4376ef4` live baseline; docs/tag `2532de7` (`eval-baseline-2026-08`) |
| **T00.5** | C0/C1 controller_backend truth | T00 | Done | `e5d91ce` |
| **T01** | maintenance-evals schemas/manifests | T00.5 | Ready | — |
| **T02** | exact-SHA replay runner + evalctl | T01 | Ready | — |
| **T03** | cost/usage telemetry + pricing | T02 | Ready | — |
| **T04** | Benchmark methodology + adapters + EXPERIMENT_FREEZE | T03 | Ready | — |
| **T05** | A/B/C0/C1 block-randomized context ablation | T04 | Ready | — |
| **T06** | SWE-CI + SWE-Chain local E2E | T05 | Ready | — |
| **T07** | Longitudinal D/E | T06 | Ready | — |
| **T08** | Frontier F/G | T06 | Ready | — |
| **T09** | Hybrid H + held-out | T08 | Ready | — |
| **T10** | Frozen analysis + lit synthesis + go/no-go | T09 | Ready | — |

## Hard gates

G1 trust-boundary · G2 C0/C1 telemetry truth · G3 platform freeze · G4 experiment freeze · G5 no leakage · G6 verification authority · G7 comparable arms · G8 cost traceability · G9 no silent tuning · G10 negative-transfer visibility · G11 infra separated · G12 full provenance · dual official/V10 metrics · seeded block-randomized order

## Wave log

| Wave | Date | Handoff | Next | Notes |
|------|------|---------|------|-------|
| 0 | 2026-08-16 | — | T00 | Ledger opened |
| 1 | 2026-08-16 | [034](coordinator-handoff-034.md) | T00 (deploy-verify) | Five stale CT104 write-token docs reconciled; repository-known baseline and live-cert checklist prepared; T00 remains Running with tip/tag/deploy fields TBD |
| 2 | 2026-08-16 | [034](coordinator-handoff-034.md) | T00.5 | `DEPLOY_VERIFY: PASS`; CT103+CT104 tip `4376ef4`; CT104 write tokens absent in all three workers; CT103 token/publish flag expected; image/model/Ollama inventory frozen; docs-only commit/tag SHA pending; CT102 runner version deferred to `DEEPER_EVAL` |
| 3 | 2026-08-16 | [035](coordinator-handoff-035.md) | T00.5 (deploy-verify) | `controller_backend` C0/C1 arm implemented; default stays `deterministic`; C1 routes `call_primary_model` to the `summarizer`/`MODEL_2070_*` role and fails soft; G2 telemetry on artifact, event, trajectory, CLI; `config/recursive_context.yaml` re-pinned `d438a2ee`→`8258dc95` with T00.5 freeze amendment; T00 final tagged SHA `2532de7` recorded; full tests + ruff green; T00.5 stays Running until deploy verification |
| 4 | 2026-08-16 | [035](coordinator-handoff-035.md) | T01 | `DEPLOY_VERIFY: PASS`; CT103+CT104 tip `e5d91ce`; `/readyz` ready; `V10_T005_SMOKE_OK` (`resolve_controller_backend` default/override); CT104 no Gitea write tokens; live C1 end-to-end against real 2070 deferred `DEEPER_EVAL` to T02/T05 harness smoke |
