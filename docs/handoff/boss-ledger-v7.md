# Boss ledger — V7 recursive context evaluation & controller bake-off

Epic supervisor state. Boss reads **this file first** for post-V6 work. Prior epic: [boss-ledger-v6.md](boss-ledger-v6.md). Preview origin: [boss-ledger-v7-preview.md](boss-ledger-v7-preview.md).

| Field | Value |
|-------|-------|
| **Epic name** | V7 — Recursive context evaluation and controller bake-off |
| **Origin** | Deferred V4 T12 (8d) + V6 eval export foundation |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Status doc** | This ledger + per-slice `docs/slice-v7-*.md` |
| **Integration branch** | `main` |
| **Epic status** | complete |
| **Tickets done (count)** | 5 / 5 |
| **Next ticket** | EPIC_COMPLETE |
| **Latest handoff** | [coordinator-handoff-021.md](coordinator-handoff-021.md) |
| **Coordinator waves completed** | 5 |
| **Last boss action** | 2026-07-21 — T05 DEPLOY_VERIFY PASS tip `573a777`; epic complete |
| **Lanes** | main only (serial waves) |
| **Environment constraints** | Same as V4–V6: WSL SSH; `docker compose exec -T … </dev/null`; CT103 publish-broker; CT102 CI truth; **no production memory mutation during bake-off** |

## Done condition

All tickets **T01–T05** `Done` with deploy verify PASS. Bake-off can import V6 `eval_bundle.v1` into Inspect AI, run profiles A–D with isolated memory namespaces, and emit metrics without treating shadow injection as authority or enabling unbounded recursive controllers in production.

## Already signed off (do not re-open)

- V6 complete tip `a9917b8` — [boss-ledger-v6.md](boss-ledger-v6.md)
- QA V6 SIGNED OFF tip `28292c0` — [qa-v6-ledger.md](qa-v6-ledger.md), [deploy-verify-qa-v6-20260721.md](deploy-verify-qa-v6-20260721.md)
- V7 complete tip `573a777` — this ledger; [deploy-verify-v7-t05-20260721.md](deploy-verify-v7-t05-20260721.md)

## Remaining tickets (dependency order)

Status: `Todo` | `In Progress` | `Deploy gate` | `Done` | `Blocked` | `Deferred`

| ID | Slice | Deps | Deploy smoke (minimum) | Status |
|----|-------|------|------------------------|--------|
| **T01** | **Inspect adapter** — `eval_bundle.v1` → Inspect AI tasks (framework-neutral import) | — | Import one exported bundle; Inspect task loads timeline/stages; no prod memory write | Done |
| **T02** | **Profiles A–D** — controller / context strategy ablation configs | T01 | Four named profiles selectable; each runs against same fixture bundle | Done |
| **T03** | **Metrics** — CT102 success, repair iters, fallback, policy violations, tokens/cost/time | T01 | Metrics JSON emitted per profile run; fields documented | Done |
| **T04** | **Memory isolation** — fork/reset namespaces via `memory_namespace` metadata | T01 | Profile runs cannot see each other's writebacks; prod namespace untouched | Done |
| **T05** | **Bake-off report** — longitudinal compare + negative-transfer notes; production gates | T02–T04 | Report artifact; unbounded recursion still off; shadow ≠ authority | Done |

### Parallelism policy

- Serial: T01 first; then T02 ∥ T03 ∥ T04 only if file trees stay disjoint and one deploy-verify owner; T05 last.
- Default: fully serial for safety around memory isolation.

### Explicit non-goals

- Do not enable unbounded recursive controllers in production.
- Do not treat LlamaFirewall / injection shadow results as authority.
- Do not mutate production memory during bake-off imports.
- Residual QA items moved to **V8** — [boss-ledger-v8.md](boss-ledger-v8.md) (was deferred during V7)

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-21 | — | T01 | Epic opened; QA V6 signed off `28292c0` |
| 1 | 2026-07-21 | [coordinator-handoff-017.md](coordinator-handoff-017.md) | T02 | T01 Done tip `b1a8a38` |
| 2 | 2026-07-21 | [coordinator-handoff-018.md](coordinator-handoff-018.md) | T03 | T02 Done tip `234e248` |
| 3 | 2026-07-21 | [coordinator-handoff-019.md](coordinator-handoff-019.md) | T04 | T03 Done tip `198eabf` |
| 4 | 2026-07-21 | [coordinator-handoff-020.md](coordinator-handoff-020.md) | T05 | T04 Done tip `47724d1`; [deploy-verify-v7-t04-20260721.md](deploy-verify-v7-t04-20260721.md) |
| 5 | 2026-07-21 | [coordinator-handoff-021.md](coordinator-handoff-021.md) | EPIC_COMPLETE | T05 Done tip `573a777`; [deploy-verify-v7-t05-20260721.md](deploy-verify-v7-t05-20260721.md); epic complete |

## Boss prompt skeleton

```text
EPIC: V7 recursive context evaluation & controller bake-off — finish T01–T05
per docs/handoff/boss-ledger-v7.md.

RULES:
1. Orient from this ledger only; one slice per wave.
2. DEPLOY_VERIFY must PASS before marking Done / advancing.
3. Never mutate production memory; bake-off namespaces only.
4. Environment: CT103 192.168.4.62 / CT104 192.168.4.63; WSL SSH deploy key.
```
