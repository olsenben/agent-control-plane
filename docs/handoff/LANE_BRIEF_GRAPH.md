# Lane brief — Graph (T05 → T06 → T07)

**Worktree:** `ai-sdlc-lab/agent-control-plane-lane-graph`  
**Branch:** `epic/lane-graph-t05-t07` (from `5908ca0`)  
**Read first:** `docs/handoff/lanes.md`, `docs/handoff/boss-ledger.md`, `docs/epic-orchestration.md`  
**Skill:** `.cursor/skills/v4-slice-coordinator` (one ticket at a time, then stop for deploy gate)

## Ownership

Implement **only** T05, then T06, then T07 — serial inside this lane. Do not start T08+.

| ID | Slice | Acceptance (ledger smoke) |
|----|-------|---------------------------|
| T05 | 8a Orbit-style code + SDLC/evidence edges | `agentctl graph` shows new edge types + provenance; blast-radius still fail-soft |
| T06 | 8b Preflight + graph coverage / missing_edges | Preflight JSON includes coverage; heuristic uses missing_edges |
| T07 | 8c Conditional 2070 recursive context | `recursive_context_required=true` → `recursive_context_result.v1`; false path skips 2070 |

V4 plan anchors: Orbit edges (~§ Orbit-style graph), Phase 20 / §8a–8c in impl order.

## Hard stops

- **Do not** `git push` to `main`. Push this feature branch only; open/update a PR.
- **Do not** SSH deploy or pin tips on CT103/CT104. After each ticket is code-complete + tests green + slice doc updated, stop with `stopped_reason: ticket_ready_for_merge` and wait for deploy-verify owner PASS before starting the next ticket.
- **Do not** edit identity/ack / `acting_identity` / invoker comment UX (T10 lane).
- Run `ruff check .` before commits. Commit/push **branch** when ready; do not amend shared history.

## Scope hints

- Prefer `src/agent_control/graph/**`, preflight modules, recursive-context worker wiring, CLI `agentctl graph` / `agentctl rlm`.
- Extend existing graph (snapshot, blast-radius, context-pack) — do not rewrite authority boundaries.
- Blast-radius remains fail-soft; graph required ≠ graph is ground truth.

## Return payload

```text
lane: graph
ticket_id: T05|T06|T07
branch: epic/lane-graph-t05-t07
pr_url: …
stopped_reason: ticket_ready_for_merge | blocker | context_handoff
blocker: none | <one line>
```
