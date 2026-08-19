# Handoff — coordinator-handoff-058

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 058 |
| Date (UTC) | 2026-08-19 |
| Slice / ticket ID | VExp W0 (A–E) |
| Tip SHA (ACP) | pending commit |
| Epic | Verified Experience Control Plane (not V10) |
| `stopped_reason` | `deploy_gate_pending` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-058.md
tickets_done: 5 / 5 W0 coded; deploy unverified
next_ticket_id: W0_DEPLOY_VERIFY then W1
blocker: none
stopped_reason: deploy_gate_pending
```

## Slice outcome

- Goal completed (one sentence): Additive W0 contracts landed without wiring V2 into the solver path.
- Slice docs: `docs/slice-vexp-w0-a-repo-snapshot.md`, `docs/slice-vexp-w0-b-context-pack-v2.md`, `docs/slice-vexp-w0-c-verification-contract.md`, `docs/slice-vexp-w0-e-baseline-harness.md`
- Deploy verify path / status: `pending`
- CT103 tip / CT104 tip: unset until pin

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: none yet
- Actions run IDs: pending push
- ADR IDs: ADR-0037
- Schema digest: `f4bf354020903368fa3f5d0bec266dabc0b55f698ea23398b5bc21e1e8a4f1e0`

## Decisions the next coordinator must honor

1. `authorized_records` is empty until a real authorization decision exists; v1 memory is `compatibility.legacy_prior_memory`.
2. `can_finalize_production_episode` is derived from `authority_domain == ct102_production`.
3. Do not freeze retriever / applicability / repair / episode Protocols in W0.
4. W0-E SKIP is forbidden on the integration tip (`VEXP_W0_ALLOW_COMPAT_SKIP` must be unset).
5. Do not append this work to boss-ledger-v10.md.

## Next coordinator: first actions

1. Finish local ruff/pytest if this handoff predates a green suite.
2. Fill `docs/handoff/deploy-verify-vexp-w0-YYYYMMDD.md` after CT103+CT104 pin.
3. Only then open `epic/vexp-w1-*`.

## Open risks (one line each)

- maintenance-evals has no Gitea remote; eval schema lives only in that local repo until copied/pushed separately.
- Two context schemas coexist until W1.
