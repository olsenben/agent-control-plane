# Boss ledger — Verified Experience Control Plane

Epic supervisor state. Prior: [boss-ledger-v10.md](boss-ledger-v10.md) (V10 remains WaitingHuman on T08/T09; do not mutate that ledger). Epic: [EPIC_verified_experience_control_plane.md](../../../../EPIC_verified_experience_control_plane.md). Plan: `.cursor/plans/vexp_wave_1_context_b199564c.plan.md`.

| Field | Value |
|-------|-------|
| **Epic name** | VExp — Verified Experience Control Plane |
| **Baseline tip** | `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66` (ACP); evals `5891c45` local-only |
| **Orchestration** | this ledger + [DEPLOY_VERIFY_TEMPLATE.md](DEPLOY_VERIFY_TEMPLATE.md) |
| **Integration branch** | `main` |
| **Epic status** | **running** — W1-TE Done; `GO_EVIDENCE_ONLY` + floor; production default remains v1 |
| **Tickets done** | W0 5/5; W1 coded + deploy-verified; W1-TE Done |
| **Next ticket** | Evidence-quality diagnostics on the repaired W1 result set. Do not start WAVE 2. |
| **Latest handoff** | [061](coordinator-handoff-061.md) |
| **Last boss action** | 2026-08-19 — W1 treatment-exposure repair rerun frozen; 14/14 treatment ok; 0/14 verified |
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
| W1-TE | Treatment-exposure repair | W1 Phase 4 freeze | Done | pre-invocation artifacts; repaired 14/14 treatment ok; 0/14 verified |

## W1 merge gate

- [x] W1 coded on ACP `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698`
- [x] CT103 and CT104 tip pin match that SHA
- [x] `DEPLOY_VERIFY: PASS` — [deploy-verify-vexp-w1-20260819.md](deploy-verify-vexp-w1-20260819.md)
- [x] `baseline_v1` / `context_v2_lexical` / `context_v2` fake-engine smoke
- [x] production default remains `compile_context_pack`
- [x] Phase 4 DEV bakeoff decision: **STOP_REPAIR** — [results/vexp-w1-context-v2-dev-v1](../../../../maintenance-evals/results/vexp-w1-context-v2-dev-v1) (immutable)
- [x] W1-TE repair on ACP `f367bf05a23d90d58a6614a0f0f2deeb4483ce2d`; CI/host tip `7e51983ac5a3b9fa38a6176da99ff03cdda3ee66`
- [x] `DEPLOY_VERIFY: PASS` — [deploy-verify-vexp-w1-te-20260819.md](deploy-verify-vexp-w1-te-20260819.md)
- [x] Repaired 14-slot create-only rerun: **GO_EVIDENCE_ONLY** + floor — [results/vexp-w1-context-v2-dev-v2-treatment-repair](../../../../maintenance-evals/results/vexp-w1-context-v2-dev-v2-treatment-repair)
- [x] CT102 Actions green for `7e51983` (test 931/932/933; deploy 934/935; runs 940/941/942)

Phase 4 freeze v1 remains STOP_REPAIR and must not be mutated. The repaired rerun has complete treatment exposure (14/14) and no verifier discrimination (0/14 verified; A vs B1 both_fail=6). Production default stays v1. Do not start WAVE 2 until evidence-quality diagnostics justify verify-to-repair.
