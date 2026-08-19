# Boss ledger — Verified Experience Control Plane

Epic supervisor state. Prior: [boss-ledger-v10.md](boss-ledger-v10.md) (V10 remains WaitingHuman on T08/T09; do not mutate that ledger). Epic: [EPIC_verified_experience_control_plane.md](../../../../EPIC_verified_experience_control_plane.md). Plan: `.cursor/plans/vexp_wave_0_contracts_71e52a04.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | VExp — Verified Experience Control Plane |
| **Baseline tip** | `d39206d3c2184125e9af55eccdde58f6531bcca3` (ACP); evals `a6969f8` local-only |
| **Orchestration** | this ledger + [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md) |
| **Integration branch** | `main` |
| **Epic status** | **running** — W0 merge gate **PASS**; W1 unblocked |
| **Tickets done** | 5 / 5 W0 |
| **Next ticket** | W1 (lexical/symbol, dependency/test graph, ContextBuilderV2, eval+production adapters). Memory/recursion/2070/repair remain off. |
| **Latest handoff** | [058](coordinator-handoff-058.md) |
| **Last boss action** | 2026-08-19 — W0 coded, committed, pinned CT103+CT104; [deploy-verify-vexp-w0-20260819.md](deploy-verify-vexp-w0-20260819.md) **PASS** |
| **Lanes** | main only; one deploy-verify owner |
| **Env** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; `docker compose exec -T … </dev/null` |

## W0 tickets

| ID | Slice | Deps | Status | Notes |
|----|-------|------|--------|-------|
| W0-A | RepoSnapshot | — | coded | `snapshot_id` = repo + SHA; workspace_path not identity |
| W0-B | ContextPackV2 + V1 bridge | W0-A types | coded | `authorized_records` empty; legacy_prior_memory only |
| W0-C | ExperienceVerificationResult | — | coded | digest `f4bf354020903368fa3f5d0bec266dabc0b55f698ea23398b5bc21e1e8a4f1e0` |
| W0-D | Telemetry vocabulary | — | coded | 17 names + envelope; no live ledger emit |
| W0-E | Baseline harness | W0-B | coded | SKIP forbidden on integration tip |

## W0 merge gate

- [x] ACP ruff + pytest green (978 passed)
- [x] maintenance-evals W0 tests green with compatibility comparison executed (no SKIP)
- [x] CT103 and CT104 tip pin match `d39206d3c2184125e9af55eccdde58f6531bcca3`
- [x] `DEPLOY_VERIFY: PASS` — [deploy-verify-vexp-w0-20260819.md](deploy-verify-vexp-w0-20260819.md)
- [x] no scored experiment declared; reserved split untouched
- [ ] CT102 Actions run IDs recorded (push triggered; IDs not scraped)

W1 is unblocked. Record Actions IDs opportunistically; do not block W1 on scrape.
