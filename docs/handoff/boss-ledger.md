# Boss ledger — V4 full build

Epic supervisor state. Boss reads **this file first**. Keep edits ≤5 lines per wave (plus one wave-log row).

| Field | Value |
|-------|-------|
| **Epic name** | V4 full build — Recursive context + graph completion |
| **Plan doc** | `gitea_agentic_sdlc_cursor_step_plan_v4.md` (impl order §) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Status doc** | This ledger + per-slice `docs/slice-*.md` |
| **Umbrella (active)** | [slice-v412-typed-sessions.md](../slice-v412-typed-sessions.md) |
| **Integration branch** | `main` (homelab tip on CT103/CT104); feature branches per slice PR |
| **Epic status** | in_progress |
| **Tickets done (count)** | 2 / 13 remaining track (T01–T02 done) |
| **Next ticket** | T03 |
| **Latest handoff** | coordinator-handoff-002 — T02 PASS `a7dd4c5` |
| **Coordinator waves completed** | 3 |
| **Last boss action** | 2026-07-20 — T02 (5.7) deploy verified `a7dd4c5`; next T03 |
| **Environment constraints** | WSL SSH deploy key; `docker compose exec -T … </dev/null`; no CT104 Gitea write tokens; SRT fail-closed Risk 2; CI truth = CT102 |

## Done condition

All tickets **T00–T13** in § Remaining tickets are `Done` with deploy verify PASS (or explicit `Deferred` with user approval for optional tickets T11–T13).  
Recursive context DoD items 1–12 from V4 plan satisfied on homelab. Optional bake-off (T12) may remain `Deferred`.

## Already signed off (do not re-open)

Baseline before this epic — see `architecture.md` / `AGENT_CARD.md` Last verified:

```text
Inspect/Explain/Review/Plan MVP, Slice 5–5.3, 5.4a+5.4b, 5.5a (deploy 6f170a4),
5.6a SRT, 5.8+6F.2 demo, 6A–6D, 6D.2 brokerage, 6E, 6F.1, V4.1.1 closeout
```

**T00** pins 5.5a as the epic baseline so the first wave starts cleanly at 5.6.

## Remaining tickets (dependency order)

Status: `Todo` | `In Progress` | `Deploy gate` | `Done` | `Blocked` | `Deferred`

| ID | Slice | Deps | Deploy smoke (minimum) | Status |
|----|-------|------|------------------------|--------|
| **T00** | Baseline pin — 5.5a tip on CT103+CT104 | — | Confirm tip `6f170a4` (or newer 5.5a-descendant) + `/readyz`; record in wave 0 | Done |
| **T01** | **5.6** Verification evidence gate | T00 | Session cannot finish “verified” without evidence events; fake fix shows `verification_*` / `verification_missing` per policy | Done |
| **T02** | **5.7** Selective writeback from session trace | T01 | `session_finished` → admitted `memory_record.v1`; second `/agent plan` retrieves it | Done |
| **T03** | **V4.1.2 exit** — bundle DoD 1–12 on demo-app | T02 | One review + one plan + one fake fix with queryable sessions; memory loop proven | Todo |
| **T04** | **§7** Scoped verification claims + adequacy profile | T03 | Agent-authored test claims scoped; adequacy profile documented + enforced on finish path | Todo |
| **T05** | **8a** Orbit-style code + SDLC/evidence graph edges | T03 | `agentctl graph` shows new edge types + provenance; blast-radius still fail-soft | Todo |
| **T06** | **8b** Preflight consumes graph coverage / missing_edges | T05, T01 | Preflight JSON includes coverage; heuristic uses missing_edges | Todo |
| **T07** | **8c** Conditional 2070 recursive context worker | T06 | `recursive_context_required=true` path returns `recursive_context_result.v1`; false path skips 2070 | Todo |
| **T08** | **§9** Recursive Qwen loop (evidence + CI retries) | T07, T01 | Bounded retry on CI fail with evidence-selected context; no unbounded loop | Todo |
| **T09** | Non-demo **6F.2** staged expand (ACP allowlist only) | T03 | Observe → repair-no-publish → one-class publish on ACP; ADR if scope widens | Todo |
| **T10** | Invocation ack + acting vs invoker identity | T03 | Start + terminal comments; invoker audit fields on session | Todo |
| **T11** | **§10** Read-only MCP graph/memory | T05 | MCP read tools only; no write surface | Todo |
| **T12** | **8d** Controller bake-off (optional) | T07 | Deterministic vs small-transformer vs recurrent metrics; **may Deferred** | Todo |
| **T13** | **§11** Patch tournaments / rewards (experiment flag) | T08 | Flag-gated; no default enable | Todo |

### Parallelism policy

- **Serial by default:** T00→T01→T02→T03.
- After T03: T04 ∥ T05 allowed (different owners); T06 waits on T05; T07 waits on T06.
- T09 / T10 after T03; do not parallelize two Risk-2 enablement tracks.
- T11 after T05; T12/T13 never block epic done if user marks Deferred.

### Backlog (not in done count)

AgentFacts-lite, memory-as-governance, review replay console, architecture drift detector, SARIF, gated self-improvement PRs — spawn a **new** epic ledger when ready.

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-20 | — | T01 | Baseline 5.5a tip superseded by 5.6 tip `8df60fc` |
| 1 | 2026-07-20 | — | T02 | T01 5.6 deploy verify PASS `8df60fc` |
| 2 | 2026-07-20 | coordinator-handoff-002.md | T02 | T02 5.7 implemented; deploy_gate_pending |
| 3 | 2026-07-20 | coordinator-handoff-002.md | T03 | T02 5.7 deploy verify PASS `a7dd4c5` |

## Boss prompt skeleton (fill from this ledger)

```text
EPIC: V4 full build — finish remaining tickets T00–T13 per docs/handoff/boss-ledger.md.

RULES (mandatory):
1. Orchestration only in boss mode; one slice per coordinator wave.
2. Do NOT treat slice completion as epic completion — continue to next Todo whose deps are Done.
3. Read epic-orchestration.md, this ledger, and the slice doc for the ticket.
4. Honor deploy gate: DEPLOY_VERIFY_TEMPLATE must PASS before marking ticket Done.
5. {{IF_FIRST_WAVE}} Start at Next ticket (T00). {{/IF_FIRST_WAVE}}
   {{IF_CONTINUATION}} Continue from handoff: {{Latest handoff}} — resume at stated next_ticket_id. {{/IF_CONTINUATION}}
6. When handing off, write docs/handoff/coordinator-handoff-NNN.md from HANDOFF_TEMPLATE.md.
7. Return compact: handoff_path, tickets_done/14, next_ticket_id, blocker, stopped_reason.

Environment: CT103 192.168.4.62 / CT104 192.168.4.63; WSL SSH; publish-broker only; CT102 CI truth.
```
