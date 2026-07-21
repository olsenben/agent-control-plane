# Boss ledger — V6 observable, attributable, secure sessions

Epic supervisor state. Boss reads **this file first** for post-V5 work. Prior epic: [boss-ledger-v5.md](boss-ledger-v5.md) (V6 complete when all tickets Done).

| Field | Value |
|-------|-------|
| **Epic name** | V6 — Observable, attributable, and secure agent sessions |
| **Plan doc** | `.cursor/plans/v6_operations_trust_epic_60bcf87e.plan.md` |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Status doc** | This ledger + per-slice `docs/slice-v6-*.md` |
| **Integration branch** | `main` |
| **Epic status** | in progress |
| **Tickets done (count)** | 7 / 8 |
| **Next ticket** | T08 |
| **Latest handoff** | [coordinator-handoff-015.md](coordinator-handoff-015.md) |
| **Coordinator waves completed** | 7 |
| **Last boss action** | 2026-07-21 — T07 DEPLOY_VERIFY PASS `70de9a3` |
| **Lanes** | main only (serial waves) |
| **Environment constraints** | Same as V4/V5: WSL SSH; `docker compose exec -T … </dev/null`; CT103 publish-broker; CT102 CI truth |

## Done condition

All tickets **T01–T08** `Done` with deploy verify PASS. Ledger canonical; OTel nonblocking; Agent Observatory live; no human PAT for agent mutations.

## Already signed off (do not re-open)

V5 complete tip `09f8340` — see [boss-ledger-v5.md](boss-ledger-v5.md).

## Remaining tickets (dependency order)

| ID | Slice | Deps | Deploy smoke (minimum) | Status |
|----|-------|------|------------------------|--------|
| **T01** | Trace, provenance, observation contract | — | `trace_id` on session; provenance on context pack; projection sequence monotonic; session completes with OTel down | Done |
| **T02** | Session status reducer + Gitea comment projection | T01 | Single upserted comment; no stale overwrite; invocation-rejected matrix | Done |
| **T03** | Agent Observatory + replay | T02 | `/observe/sessions/{run_id}` loads; SSE event; Observe link in comment | Done |
| **T04** | LiteLLM gateway + bounded failover | T01 | Chaos test proves fallback or visible failure; attempt budget enforced | Done |
| **T05** | Authorization decisions + attribution | T01 | Separate predicate checks; pre-publish recheck; commit trailers | Done |
| **T06** | Injection scanner shadow | T01, T03 | Shadow assessment in Observatory; no authority grant from scanner | Done |
| **T07** | NL invocation + clarification lifecycle | T05, T06 | `@agent` resolves; `/agent` unchanged; invocation_id FSM | Done |
| **T08** | Frozen eval export + V7 handoff | T03–T07 | Content-addressed `eval_bundle_sha256`; production memory unchanged | Todo |

### Wave order (serial)

```text
Scaffold → T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08
```

### Out of scope

- V7 recursive-controller bake-off (see [boss-ledger-v7-preview.md](boss-ledger-v7-preview.md))
- LlamaFirewall blocking mode (shadow only in T06)
- Semantic Router mandatory on T07 day one

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-21 | — | T01 | Ledger + slice stubs created |
| 2 | 2026-07-21 | [coordinator-handoff-011.md](coordinator-handoff-011.md) | T03 | T02 Done tip `66f885e`; V6_T02_SMOKE_OK |
| 4 | 2026-07-21 | [coordinator-handoff-012.md](coordinator-handoff-012.md) | T05 | T04 Done tip `d5e4e93`; V6_T04_SMOKE_OK |
| 5 | 2026-07-21 | [coordinator-handoff-013.md](coordinator-handoff-013.md) | T06 | T05 Done tip `1dff508`; V6_T05_SMOKE_OK |
| 6 | 2026-07-21 | [coordinator-handoff-014.md](coordinator-handoff-014.md) | T07 | T06 Done tip `6cc8264`; V6_T06_SMOKE_OK |
| 7 | 2026-07-21 | [coordinator-handoff-015.md](coordinator-handoff-015.md) | T08 | T07 Done tip `70de9a3`; V6_T07_SMOKE_OK |

## Boss prompt skeleton

```text
EPIC: V6 observable sessions — finish T01–T08 per docs/handoff/boss-ledger-v6.md.
```
