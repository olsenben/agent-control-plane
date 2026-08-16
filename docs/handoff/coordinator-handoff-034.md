# Handoff — coordinator-handoff-034

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 034 |
| Date (UTC) | 2026-08-16 |
| Slice / ticket ID | V10 T00 |
| Tip SHA (ACP) | Live-certified baseline `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb`; final docs/tag SHA `PENDING_COMMIT` |
| Epic | V10 Maintenance Evaluation & Economic Bake-off |
| `stopped_reason` | `context_handoff` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-034.md
tickets_done: 1 / 12
next_ticket_id: T00.5
blocker: none
stopped_reason: context_handoff
```

## Slice outcome

- Goal completed: Reconciled the five stale CT104 write-token documents and live-certified the V10 platform/trust-boundary baseline.
- Slice doc path: `docs/evals/V10_BASELINE.md`
- Deploy verify path / status: `docs/handoff/deploy-verify-v10-t00-20260816.md` / `pass`
- CT103 tip / CT104 tip: `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb` / `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb`

T00 is Done. The live trust boundary, host tips, service image IDs, model inventory, and Ollama versions are certified. The orchestrator still must commit these docs and create `eval-baseline-2026-08` at the resulting docs-only SHA; that administrative closeout must not include behavior changes.

## Evidence pointers (paths / IDs only)

- Gitea issue / PR: not supplied
- Actions run IDs: not supplied
- Session / run IDs: live-cert evidence supplied out of band
- ADR IDs: `ADR-0004`, `ADR-0006`
- Trust-boundary evidence: `docs/secrets-boundaries.md`, `docs/slice-6d2-ct103-publish-brokerage.md`
- Baseline evidence: `docs/evals/V10_BASELINE.md`
- Deploy checklist: `docs/handoff/deploy-verify-v10-t00-20260816.md`

## Decisions the next coordinator must honor

1. CT103 is the sole Gitea mutation authority; CT104 may retain read-only clone/fetch credentials but no Gitea write token.
2. The live-deployed baseline tip is `4376ef417e29f14bf05d2fcee89c0ab2739f2ddb`; preserve Observatory contracts `observation_projection.v1` / `observe_event.v1` sourced from V9 tip `fba0846624fc5dfbdf762b06391d181ef9ce7beb`.
3. T00.5 must use configured `MODEL_2070_NAME=qwen2.5-coder:3b`. The 7B model is available on the host but is not the live configured baseline.

## Next coordinator: first actions

1. Commit only the T00 documentation changes and create `eval-baseline-2026-08` at that docs-only commit; update the final tagged SHA field during closeout.
2. Begin T00.5 from the certified baseline without changing the configured 2070 model implicitly.
3. Inventory CT102 runner/version before scored evaluation and record external fallback use explicitly.

## Open risks (one line each)

- The shared working tree contains substantial pre-existing changes; the orchestrator must isolate the T00 documentation set when committing.
- The final docs/tag SHA is necessarily unknown until this documentation is committed.
- CT102 runner/version remains `PENDING_LIVE_CERT` / `DEEPER_EVAL`.
- External health reports OpenAI URLs and fallbacks `gpt-4.1` / `gpt-4o-mini`; evaluation routing must prevent accidental paid fallback contamination.
