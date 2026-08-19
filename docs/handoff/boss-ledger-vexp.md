# Boss ledger — Verified Experience Control Plane

Epic supervisor state. Prior: [boss-ledger-v10.md](boss-ledger-v10.md) (V10 remains WaitingHuman on T08/T09; do not mutate that ledger). Epic: [EPIC_verified_experience_control_plane.md](../../../../EPIC_verified_experience_control_plane.md). Plan: `.cursor/plans/vexp_wave_0_contracts_71e52a04.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | VExp — Verified Experience Control Plane |
| **Baseline tip** | pending W0 merge SHA |
| **Orchestration** | this ledger + [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md) |
| **Integration branch** | `main` |
| **Epic status** | **running** — W0 implementation landed locally; deploy gate open |
| **Tickets done** | 5 / 5 W0 slices coded; 0 / 5 deploy-verified |
| **Next ticket** | W0 merge gate (`DEPLOY_VERIFY` then W1). Do not open `epic/vexp-w1-*` until PASS. |
| **Latest handoff** | [058](coordinator-handoff-058.md) |
| **Last boss action** | 2026-08-19 — W0-A..E implemented on the working tree; ADR-0037 proposed |
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

- [ ] ACP ruff + pytest green
- [ ] maintenance-evals W0 tests green with compatibility comparison executed (no SKIP)
- [ ] CT102 `ci` + `deploy` + `deploy-ct104` green
- [ ] CT103 and CT104 tip pin match
- [ ] `DEPLOY_VERIFY: PASS`
- [ ] no scored experiment declared; reserved split untouched

W1 is blocked until every box is checked.
