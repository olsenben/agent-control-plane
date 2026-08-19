# Handoff — coordinator-handoff-059

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 059 |
| Date (UTC) | 2026-08-19 |
| Slice / ticket ID | VExp W1 (0, A–F) deploy verify |
| Tip SHA (ACP) | `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698` |
| maintenance-evals SHA | `f5a1c56c2d19c70aa49766d16cd0c577eb705e05` (local-only) |
| Epic | Verified Experience Control Plane (not V10) |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-059.md
tickets_done: W0 5/5; W1 coded + DEPLOY_VERIFY PASS
next_ticket_id: W1 Phase 4 DEV bakeoff
blocker: none
stopped_reason: context_handoff
```

## Slice outcome

- Goal completed (one sentence): Exact-SHA ContextPack V2 is live on the eval solver path without flipping production; CT103+CT104 pinned; deploy verify PASS.
- Slice docs: `docs/slice-vexp-w1-*.md`
- Deploy verify path / status: [deploy-verify-vexp-w1-20260819.md](deploy-verify-vexp-w1-20260819.md) `pass`
- CT103 tip / CT104 tip: `19db1f2c21a00dd17f65e8bc1a934f7e4f1b0698` both

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: none
- Actions run IDs: pending scrape (push `35e155d..19db1f2`)
- ADR IDs: ADR-0038
- Fake-engine sessions: `sess-eval-cbdba96bd0e84f45b834ac656133a0c7` (A), `sess-eval-bd30595e9fac47f7be267946e0b87f81` (B0), `sess-eval-8b8623e155f54975998234a3dcf33edd` (B1)

## Decisions the next coordinator must honor

1. Production default stays `CONTEXT_MODE=baseline_v1` / `compile_context_pack`. Do not flip from Phase 4 even on `GO_VERIFIED` until an explicit follow-up.
2. Discriminated job transport: engine renders by `schema_version`; do not pre-render V2 to opaque text.
3. Exact-SHA workspaces only; providers never git-mutate; do not use graph branch-tip cache as the V2 evidence workspace.
4. Memory/recursion/2070/repair stay off. `authorized_records` stays empty. `legacy_prior_memory` must not appear in `render_v2`.
5. Do not mutate `boss-ledger-v10.md` or frozen V10 manifests 1.3.0 / 1.6.0 / 1.9.0.
6. Reference-patch recall is post-hoc only.

## Next coordinator: first actions

1. Phase 4 DEV bakeoff: A=`baseline_v1`, B0=`context_v2_lexical`, B1=`context_v2` on 3080 `qwen2.5-coder:14b` Q4_K_M.
2. Wire `context_mode` through the evals dispatch request (stub yaml exists; runner does not yet send the field).
3. `scored=false` until create-only freeze. Decision: `GO_VERIFIED` / `GO_EVIDENCE_ONLY` / `STOP_REPAIR`.
4. Do not inspect reserved val/test splits.

## Open risks (one line each)

- Typed `RLMJob.context_pack` is still v1-only, so live Gitea cannot enqueue a V2 pack.
- maintenance-evals has no Gitea remote; Phase 4 artifacts stay local until copied.
- Full DEV corpus × three arms on 14B will be wall-clock heavy; start with treatment-integrity then scale.
