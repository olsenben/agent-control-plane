# Boss ledger — V5 governance & transparency

Epic supervisor state. Boss reads **this file first** for post-V4 work. Prior epic: [boss-ledger.md](boss-ledger.md) (V4 complete; T12 Deferred).

| Field | Value |
|-------|-------|
| **Epic name** | V5 governance & transparency — AgentFacts, memory gates, replay, drift |
| **Plan doc** | `gitea_agentic_sdlc_cursor_step_plan_v4.md` §0.4–§0.5 Future experiments + §29 Future |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) (same loop; this ledger) |
| **Status doc** | This ledger + per-slice `docs/slice-*.md` |
| **Umbrella** | [slice-v5-t01-agentfacts-lite.md](../slice-v5-t01-agentfacts-lite.md) |
| **Integration branch** | `main` |
| **Epic status** | complete |
| **Tickets done (count)** | 6 / 6 |
| **Next ticket** | EPIC_COMPLETE / none |
| **Latest handoff** | [coordinator-handoff-009.md](coordinator-handoff-009.md) |
| **Coordinator waves completed** | 6 |
| **Last boss action** | 2026-07-20 — T06 DEPLOY_VERIFY PASS `7b01adc`; epic complete |
| **Lanes** | [lanes.md](lanes.md) — retired; main only until dual-lane needed |
| **Environment constraints** | Same as V4: WSL SSH; `docker compose exec -T … </dev/null`; CT103 publish-broker; CT102 CI truth; SRT fail-closed Risk 2 |

## Done condition

All tickets **T01–T06** `Done` with deploy verify PASS (or explicit `Deferred` with user approval). No default enable of Risk-2 expansion beyond current ACP lint allowlist without a separate ADR wave.

## Already signed off (do not re-open)

V4 full build tip `16738d0` — see prior [boss-ledger.md](boss-ledger.md) and [AGENT_CARD.md](../AGENT_CARD.md).

V5 T01 tip `bdbdc99` — AgentFacts-lite; see [slice-v5-t01-agentfacts-lite.md](../slice-v5-t01-agentfacts-lite.md), ADR-0020.

V5 T02 tip `f2b8ce9` — Memory-as-governance; see [slice-v5-t02-memory-as-governance.md](../slice-v5-t02-memory-as-governance.md), ADR-0021.

V5 T04 tip `a8c5373` — Architecture drift detector; see [slice-v5-t04-architecture-drift.md](../slice-v5-t04-architecture-drift.md), ADR-0022.

V5 T03 tip `5ca8d78` (feature `b7fa044`) — Review replay console; see [slice-v5-t03-review-replay-console.md](../slice-v5-t03-review-replay-console.md), ADR-0023. Combined dual-lane verify covered T04 smoke on same tip.

V5 T05 tip `60f30bb` — SARIF ingest; see [slice-v5-t05-sarif-ingest.md](../slice-v5-t05-sarif-ingest.md), ADR-0024.

V5 T06 tip `7b01adc` — Gated self-improvement; see [slice-v5-t06-gated-self-improvement.md](../slice-v5-t06-gated-self-improvement.md), ADR-0025.

## Remaining tickets (dependency order)

Status: `Todo` | `In Progress` | `Deploy gate` | `Done` | `Blocked` | `Deferred`

| ID | Slice | Deps | Deploy smoke (minimum) | Status |
|----|-------|------|------------------------|--------|
| **T01** | **AgentFacts-lite** — signed capability / limitation manifests | — | Machine + human card stay in sync; unsigned or stale manifest fails a documented check | Done |
| **T02** | **Memory-as-governance** — block fix on repeated_failed_fix history | T01 | Fix path deny when memory says repeated failure class without new evidence; audit event emitted | Done |
| **T03** | **Review replay console** — issue → context → model → policy → memory | T01 | Operator can replay one finished review session end-to-end from durable artifacts | Done |
| **T04** | **Architecture drift detector** — ADR vs graph edges | T01 | Drift report lists missing/extra edges vs ADR facts; fail-soft on CT103 | Done |
| **T05** | **SARIF ingest** — findings → graph/security nodes | T03 or T04 | Sample SARIF attaches as evidence nodes; Risk 0/1 only | Done |
| **T06** | **Gated self-improvement** — workflow/prompt proposals as PRs only | T02, T03 | Agent opens PR for prompt/workflow change; no in-prod self-edit | Done |

### Parallelism policy

- **Serial by default:** T01 → T02; T01 → T03∥T04 after T01 Done; T05 after T03 or T04; T06 last.
- Optional dual-lane only for **T03 ∥ T04** (disjoint files). One deploy-verify owner.
- Do **not** enable T12 (V4 bake-off) from this epic unless the user reopens it explicitly.

### Out of scope (stay Deferred / other epic)

- T12 controller bake-off (V4 optional 8d)
- Broadening 6F.2 beyond ACP + `lint_failure`
- Enabling `experiments.patch_tournament` / `rl_reward_logging` by default

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-20 | — | T01 | Ledger created; V4 closed |
| 1 | 2026-07-20 | [coordinator-handoff-003.md](coordinator-handoff-003.md) | T02 | T01 Done tip `bdbdc99`; Actions 705–707 |
| 2 | 2026-07-20 | [coordinator-handoff-004.md](coordinator-handoff-004.md) | T03 | T02 Done tip `f2b8ce9`; Actions 711–713 |
| 3 | 2026-07-20 | [coordinator-handoff-006.md](coordinator-handoff-006.md) | T03 | T04 Done tip `a8c5373`; Actions 717–719; T03 dual-lane concurrent |
| 4 | 2026-07-20 | [coordinator-handoff-007.md](coordinator-handoff-007.md) | T05 | T03 Done tip `5ca8d78`; Actions 723–725; T04 re-smoke OK; dual-lane closed |
| 5 | 2026-07-20 | [coordinator-handoff-008.md](coordinator-handoff-008.md) | T06 | T05 Done tip `60f30bb`; Actions 729–731; SARIF evidence nodes OK |
| 6 | 2026-07-20 | [coordinator-handoff-009.md](coordinator-handoff-009.md) | EPIC_COMPLETE | T06 Done tip `7b01adc`; Actions 742–744; PR #31; epic complete |

## Boss prompt skeleton

```text
EPIC: V5 governance & transparency — finish T01–T06 per docs/handoff/boss-ledger-v5.md.

RULES:
1. Orient from this ledger only; one slice per wave.
2. DEPLOY_VERIFY must PASS before marking Done / advancing.
3. Prefer finishing proof over starting new tickets when deploy is open.
4. Environment: CT103 192.168.4.62 / CT104 192.168.4.63; WSL SSH deploy key.
```
