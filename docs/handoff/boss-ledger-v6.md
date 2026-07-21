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
| **Tickets done (count)** | 1 / 8 |
| **Next ticket** | T02 |
| **Latest handoff** | [coordinator-handoff-010.md](coordinator-handoff-010.md) |
| **Coordinator waves completed** | 1 |
| **Last boss action** | 2026-07-21 — T01 DEPLOY_VERIFY PASS `ae4f5e4` |
| **Lanes** | main only (serial waves) |
| **Environment constraints** | Same as V4/V5: WSL SSH; `docker compose exec -T … </dev/null`; CT103 publish-broker; CT102 CI truth |

## Done condition

All tickets **T01–T08** `Done` with deploy verify PASS. Ledger canonical; OTel nonblocking; Agent Observatory live; no human PAT for agent mutations.

## Already signed off (do not re-open)

V5 complete tip `09f8340` — see [boss-ledger-v5.md](boss-ledger-v5.md).

## Remaining tickets (dependency order)

Status: `Todo` | `In Progress` | `Deploy gate` | `Done` | `Blocked` | `Deferred`

| ID | Slice | Deps | Deploy smoke (minimum) | Status |
|----|-------|------|------------------------|--------|
| **T01** | Trace, provenance, observation contract | — | `trace_id` on session; provenance on context pack; projection sequence monotonic; session completes with OTel down | Done |
| **T02** | Session status reducer + Gitea comment projection | T01 | Single upserted comment; no stale overwrite; invocation-rejected matrix | Todo |
| **T03** | Agent Observatory + replay | T02 | `/observe/sessions/{run_id}` loads; SSE event; Observe link in comment | Todo |
| **T04** | LiteLLM gateway + bounded failover | T01 | Chaos test proves fallback or visible failure; attempt budget enforced | Todo |
| **T05** | Authorization decisions + attribution | T01 | Separate predicate checks; pre-publish recheck; commit trailers | Todo |
| **T06** | Injection scanner shadow | T01, T03 | Shadow assessment in Observatory; no authority grant from scanner | Todo |
| **T07** | NL invocation + clarification lifecycle | T05, T06 | `@agent` resolves; `/agent` unchanged; invocation_id FSM | Todo |
| **T08** | Frozen eval export + V7 handoff | T03–T07 | Content-addressed `eval_bundle_sha256`; production memory unchanged | Todo |

### Wave order (serial)

```text
Scaffold → T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08
```

T04 and T05 may dual-lane after T01 only if explicitly opened; default is serial.

### Out of scope

- V7 recursive-controller bake-off (V4 T12 Deferred)
- LlamaFirewall blocking mode (shadow only in T06)
- Semantic Router mandatory on T07 day one

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-21 | — | T01 | Ledger + slice stubs created |
| 1 | 2026-07-21 | [coordinator-handoff-010.md](coordinator-handoff-010.md) | T02 | T01 Done tip `ae4f5e4`; Actions green; V6_T01_SMOKE_OK |

## Boss prompt skeleton

```text
EPIC: V6 observable sessions — finish T01–T08 per docs/handoff/boss-ledger-v6.md.

RULES:
1. Orient from this ledger only; one slice per wave.
2. DEPLOY_VERIFY must PASS before marking Done / advancing.
3. No pause between waves after deploy/doc update complete.
4. Environment: CT103 192.168.4.62 / CT104 192.168.4.63; WSL SSH deploy key.
```
