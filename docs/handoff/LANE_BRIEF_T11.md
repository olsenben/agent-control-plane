# Lane brief — T11 Read-only MCP

**Worktree:** `ai-sdlc-lab/agent-control-plane-lane-t11`  
**Branch:** `epic/lane-t11-mcp` (from `8523a0e`)  
**Read:** `docs/handoff/lanes.md`, `docs/handoff/boss-ledger.md` (T11), V4 plan Phase 24 / impl order item 10  
**Skill:** `.cursor/skills/v4-slice-coordinator`

## Ownership

**T11 only** — Read-only MCP exposure of bounded graph/memory queries.

Ledger smoke: MCP read tools only; no write surface.

Plan anchors: `get_context_capsule`, `get_relevant_adr_facts`, `get_finding`, `get_verification_state`, `get_policy`, `get_run_trajectory` and/or graph queries (`find_callers`, `affected_tests`, `dependency_path`, `explain_blast_radius`, `get_context_pack`) — keep **read-only**, schema-validated, size-bounded; `docs/mcp.md` for Inspector.

## Hard stops

- Do **not** push `main` or SSH deploy / tip-pin.
- Do **not** expose write, shell, git push, ADR mutation, or state mutation tools.
- Do **not** change Qwen CI-retry loop (T08) or Risk-2 repair allowlist (T09).
- Hold merge until deploy-verify owner clears (prefer after T08 tip green).
- `ruff check .` before commit; feature branch + PR only.

## Return

```text
lane: t11
ticket_id: T11
branch: epic/lane-t11-mcp
pr_url: …
stopped_reason: ticket_ready_for_merge | blocker
blocker: none | …
```
