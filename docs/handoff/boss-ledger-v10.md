# Boss ledger — V10 Maintenance Evaluation & Economic Bake-off

Epic supervisor state. Prior: [boss-ledger-v9.md](boss-ledger-v9.md) (complete). Epic: [boss-ledger-v10-maintenance-evaluation-revised.md](../boss-ledger-v10-maintenance-evaluation-revised.md). Plan: `.cursor/plans/v10_eval_bakeoff_30f4388b.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | V10 — Maintenance Evaluation & Economic Bake-off |
| **Baseline tip** | `4376ef4` live-certified; docs/tag SHA `2532de7` (`eval-baseline-2026-08`) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) + V10 plan dual-freeze discipline |
| **Integration branch** | `main` |
| **Epic status** | in_progress |
| **Tickets done** | 9 / 12 |
| **Next ticket** | T08 |
| **Latest handoff** | [042](coordinator-handoff-042.md) |
| **Last boss action** | 2026-08-16 — T07 executed the D/E longitudinal batch for real on the frozen synthetic corpus and sealed it; the H3 instrument is verified but H3 itself is unclaimed pending `EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS` |
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
| **T01** | maintenance-evals schemas/manifests | T00.5 | Done | `maintenance-evals@e9269e4` |
| **T02** | exact-SHA replay runner + evalctl | T01 | Done | `maintenance-evals` working tree; coordinator commit pending |
| **T03** | cost/usage telemetry + pricing | T02 | Done | `maintenance-evals` working tree; coordinator commit pending |
| **T04** | Benchmark methodology + adapters + EXPERIMENT_FREEZE | T03 | Done (WaitingHuman external licences/frontier pricing) | `maintenance-evals@b282f6d`; tag `v10-experiment-freeze-2026-08-16` |
| **T05** | A/B/C0/C1 block-randomized context ablation | T04 | Done (harness); WaitingHuman official ARB/SWE-CI H1 | result set `836086c8…` |
| **T06** | SWE-CI + SWE-Chain local E2E | T05 | Done (harness); WaitingHuman official SWE-CI/SWE-Chain | batch `1750165e…`; provisional C0 only |
| **T07** | Longitudinal D/E | T06 | Done (real batch + freeze); H3 unclaimed pending agent execution | `maintenance-evals@002fdc0`; result set `6f2fe308…` |
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
| 5 | 2026-08-16 | [036](coordinator-handoff-036.md) | T02 | T01 created evaluation-only `maintenance-evals` repo at `e9269e4` with frozen typed/schema contracts, four pre-registration manifests, dual verification metrics, scored failure taxonomy, methodology, and green tests; deploy N/A |
| 6 | 2026-08-16 | [037](coordinator-handoff-037.md) | T03 | T02 added exact-SHA isolated workspaces, immutable replay audit records, injectable trusted control-plane dispatch, terminal AgentSession/result-SHA/verification collection, failure separation, seeded block-randomized ordering, and `evalctl run/replay/validate-run`; 11 tests + ruff green; deploy N/A |
| 7 | 2026-08-16 | [038](coordinator-handoff-038.md) | T04 | T03 normalized session/trajectory local, recursive-controller, frontier, wall-time, attempts, and CI telemetry without zero-filling; added source/missing-field provenance, separate local GPU seconds, versioned pricing SHA provenance, Decimal paid-API calculation, explicit unknown usage/price statuses, cost-accounting docs, and tests; 16 tests + ruff green; deploy N/A |
| 8 | 2026-08-16 | [039](coordinator-handoff-039.md) | T05 | T04 sealed benchmark registry, adapters, splits, custom longitudinal corpus, manifests, and statistical plan under `v10-experiment-freeze-2026-08-16`; official external corpora remain WaitingHuman |
| 9 | 2026-08-16 | [040](coordinator-handoff-040.md) | T06 | T05 implemented frozen A/B/C0/C1 block scheduling at seed `20260815`, fail-closed official scoring, C0/C1 telemetry checks, and a create-only 24-slot synthetic harness result freeze (`scored=false`, no H1 claim); official ARB/SWE-CI H1 remains WaitingHuman |
| 10 | 2026-08-16 | [041](coordinator-handoff-041.md) | T07 | T06 implemented benchmark/task/repeat block scheduling, required E2E telemetry and leakage guards, separate 24-slot SWE-CI/SWE-Chain synthetic freezes, and a harness-only `local-recursive-fallback` selection labeled `PROVISIONAL_NOT_FOR_H2`; official success rates remain unclaimed and WaitingHuman |
| 11 | 2026-08-16 | [042](coordinator-handoff-042.md) | T08 | T07 built the reusable-memory store, hash-chained audit ledger, phase-split validity semantics and frozen D/E suite, then really executed 108 slots over the 18 dev+validation episodes: both arms saw the same 135 eligible records with D consuming 0 and E 135, `future_commits_reachable` 0 in 108/108, 42 stale retrievals retained, and 3/3 trap variants passing the official check while failing the frozen additional checks. H3 is recorded as unclaimed, not null, because no slot reached the frozen patch-authoring agent; blocker `EXECUTE_FROZEN_PLATFORM_AGENT_ON_LONGITUDINAL_CORPUS`. Test split untouched for T09 |
