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
| **Tickets done (count)** | 8 / 13 remaining track (T01–T07, T10 done) |
| **Next ticket** | T08 ∥ T11 (T12 Deferred; then T09; then T13) |
| **Latest handoff** | T10 PASS `4a9acdc` (graph tip `ee2367b`) |
| **Coordinator waves completed** | 10 |
| **Last boss action** | 2026-07-20 — wave2 lanes: T08∥T11; T12 Deferred; tip pins serialized |
| **Lanes** | [lanes.md](lanes.md) — worktrees `…-lane-t08` / `…-lane-t11` |
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
| **T03** | **V4.1.2 exit** — bundle DoD 1–12 on demo-app | T02 | One review + one plan + one fake fix with queryable sessions; memory loop proven | Done |
| **T04** | **§7** Scoped verification claims + adequacy profile | T03 | Agent-authored test claims scoped; adequacy profile documented + enforced on finish path | Done |
| **T05** | **8a** Orbit-style code + SDLC/evidence graph edges | T03 | `agentctl graph` shows new edge types + provenance; blast-radius still fail-soft | Done |
| **T06** | **8b** Preflight consumes graph coverage / missing_edges | T05, T01 | Preflight JSON includes coverage; heuristic uses missing_edges | Done |
| **T07** | **8c** Conditional 2070 recursive context worker | T06 | `recursive_context_required=true` path returns `recursive_context_result.v1`; false path skips 2070 | Done |
| **T08** | **§9** Recursive Qwen loop (evidence + CI retries) | T07, T01 | Bounded retry on CI fail with evidence-selected context; no unbounded loop | In Progress |
| **T09** | Non-demo **6F.2** staged expand (ACP allowlist only) | T03 | Observe → repair-no-publish → one-class publish on ACP; ADR if scope widens | Todo |
| **T10** | Invocation ack + acting vs invoker identity | T03 | Start + terminal comments; invoker audit fields on session | Done |
| **T11** | **§10** Read-only MCP graph/memory | T05 | MCP read tools only; no write surface | In Progress |
| **T12** | **8d** Controller bake-off (optional) | T07 | Deterministic vs small-transformer vs recurrent metrics; **may Deferred** | Deferred |
| **T13** | **§11** Patch tournaments / rewards (experiment flag) | T08 | Flag-gated; no default enable | Todo |

### Parallelism policy

- **Serial by default:** T00→T01→T02→T03; T08→T13.
- **Active dual-lane (wave 2):** T08 on `epic/lane-t08-qwen-loop`; T11 on `epic/lane-t11-mcp`. **One deploy-verify owner** — see [lanes.md](lanes.md).
- **Then serial:** T09 alone (Risk-2). **Last:** T13 after T08 Done.
- **T12 Deferred** (controller bake-off).

### Backlog (not in done count)

AgentFacts-lite, memory-as-governance, review replay console, architecture drift detector, SARIF, gated self-improvement PRs — spawn a **new** epic ledger when ready.

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-20 | — | T01 | Baseline 5.5a tip superseded by 5.6 tip `8df60fc` |
| 1 | 2026-07-20 | — | T02 | T01 5.6 deploy verify PASS `8df60fc` |
| 2 | 2026-07-20 | coordinator-handoff-002.md | T02 | T02 5.7 implemented; deploy_gate_pending |
| 3 | 2026-07-20 | coordinator-handoff-002.md | T03 | T02 5.7 deploy verify PASS `a7dd4c5` |
| 4 | 2026-07-20 | — | T04 | T03 V4.1.2 exit PASS (review→plan memory loop) |
| 5 | 2026-07-20 | — | T05 | T04 adequacy deploy verify PASS `e5469f7` |
| 6 | 2026-07-20 | lanes.md | T05∥T10 | Worktrees + dual-lane spawn; tip pins owned by boss |

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
