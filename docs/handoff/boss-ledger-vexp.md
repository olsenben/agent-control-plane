# Boss ledger — Verified Experience Control Plane

Epic supervisor state. Prior: [boss-ledger-v10.md](boss-ledger-v10.md) (V10 remains WaitingHuman on T08/T09; do not mutate that ledger). Epic: [EPIC_verified_experience_control_plane.md](../../../../EPIC_verified_experience_control_plane.md). Plan: `.cursor/plans/vexp_wave_1_context_b199564c.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | VExp — Verified Experience Control Plane |
| **Baseline tip** | `2f15d82fa2122c7fbff443a0daf567442025d9e8` (ACP); evals `8ff016b` local-only |
| **Orchestration** | this ledger + [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md) |
| **Integration branch** | `main` |
| **Epic status** | **running** — W1 treatment-exposure repair in progress; production default remains v1 |
| **Tickets done** | W0 5/5; W1 coded + deploy-verified; Phase 4 STOP_REPAIR freeze recorded |
| **Next ticket** | Finish W1 treatment-exposure repair (do not start WAVE 2). |
| **Latest handoff** | [060](coordinator-handoff-060.md) |
| **Last boss action** | 2026-08-19 — treatment provenance persist-before-parse repair coded; official rerun pending |
| **Lanes** | main only; one deploy-verify owner |
| **Env** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; `docker compose exec -T … </dev/null` |

## W0 tickets

| ID | Slice | Deps | Status | Notes |
|----|-------|------|--------|-------|
| W0-A | RepoSnapshot | — | Done | `snapshot_id` = repo + SHA; workspace_path not identity |
| W0-B | ContextPackV2 + V1 bridge | W0-A types | Done | `authorized_records` empty; legacy_prior_memory only |
| W0-C | ExperienceVerificationResult | — | Done | digest `f4bf354020903368fa3f5d0bec266dabc0b55f698ea23398b5bc21e1e8a4f1e0` |
| W0-D | Telemetry vocabulary | — | Done | 17 names + envelope; no live ledger emit |
| W0-E | Baseline harness | W0-B | Done | SKIP forbidden on integration tip |

## W0 merge gate

- [x] ACP ruff + pytest green (978 passed)
- [x] maintenance-evals W0 tests green with compatibility comparison executed (no SKIP)
- [x] CT103 and CT104 tip pin match `d39206d3c2184125e9af55eccdde58f6531bcca3` (superseded live tip is W1)
- [x] `DEPLOY_VERIFY: PASS` — [deploy-verify-vexp-w0-20260819.md](deploy-verify-vexp-w0-20260819.md)
- [x] no scored experiment declared; reserved split untouched
- [ ] CT102 Actions run IDs recorded (push triggered; IDs not scraped)

## W1 tickets

| ID | Slice | Deps | Status | Notes |
|----|-------|------|--------|-------|
| W1-0 | Types | W0 | Done | EvidenceQuery / ProviderResult / ContextBuildResult; no `state_predicate` |
| W1-A | Lexical | W1-0 | Done | `rg_unavailable` is diagnostic status |
| W1-B | Symbols | W1-0 | Done | Tree-sitter + regex fallback; `language_unsupported` is status |
| W1-C | Graph | W1-0 | Done | neighbors / affected_tests / dependency_envelope; SHA-gated |
| W1-D | Builder | W1-0 | Done | pure `ContextBuilder`; no emit inside `build` |
| W1-F | Exact-SHA workspace | W1-0 | Done | `materialize_exact_sha_workspace`; providers never checkout |
| W1-E/F | Eval+prod integration | W1-A..D,F | Done | discriminated `context_pack`; production default v1 |
| W1-TE | Treatment-exposure repair | W1 Phase 4 freeze | In Progress | persist pack/render/TreatmentExposure before `engine.run`; do not mutate v1 freeze |

## W1 merge gate

- [x] W1 coded on ACP `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698`
- [x] CT103 and CT104 tip pin match that SHA
- [x] `DEPLOY_VERIFY: PASS` — [deploy-verify-vexp-w1-20260819.md](deploy-verify-vexp-w1-20260819.md)
- [x] `baseline_v1` / `context_v2_lexical` / `context_v2` fake-engine smoke
- [x] production default remains `compile_context_pack`
- [x] Phase 4 DEV bakeoff decision: **STOP_REPAIR** — [results/vexp-w1-context-v2-dev-v1](../../../../maintenance-evals/results/vexp-w1-context-v2-dev-v1)
- [ ] CT102 Actions run IDs recorded

Phase 4 freeze: 13/14 slots had treatment integrity; slot 14 (`retry-toolkit-e06` / `context_v2`, `sess-eval-509576c0e89d4e59bba1d48e0fbd806c`) failed as `evaluated_agent` (fix JSON parse + json-retry timeout) and recorded no V2 pack hashes. Verifier lift was 0/14. Production default stays v1. Frozen result set `results/vexp-w1-context-v2-dev-v1` is immutable. Do not start WAVE 2 until a repaired create-only result set has complete treatment exposure.
