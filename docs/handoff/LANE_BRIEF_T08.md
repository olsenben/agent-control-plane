# Lane brief — T08 Recursive Qwen loop

**Worktree:** `ai-sdlc-lab/agent-control-plane-lane-t08`  
**Branch:** `epic/lane-t08-qwen-loop` (from `8523a0e`)  
**Read:** `docs/handoff/lanes.md`, `docs/handoff/boss-ledger.md` (T08), V4 plan §9 / impl order item 9  
**Skill:** `.cursor/skills/v4-slice-coordinator`

## Ownership

**T08 only** — Recursive Qwen loop: evidence-selected context + **bounded** CI-grounded retries; no unbounded loop.

Ledger smoke: Bounded retry on CI fail with evidence-selected context; no unbounded loop.

Build on T07 recursive_context + T01 verification gate. Prefer wiring near existing fix/repair / CI truth paths without enabling non-demo 6F.2 (T09).

## Hard stops

- Do **not** push `main` or SSH deploy CT103/CT104.
- Do **not** implement MCP server (T11) or expand repair allowlist (T09).
- Do **not** enable T13 tournaments.
- `ruff check .` before commit; feature branch + PR only.

## Return

```text
lane: t08
ticket_id: T08
branch: epic/lane-t08-qwen-loop
pr_url: …
stopped_reason: ticket_ready_for_merge | blocker
blocker: none | …
```
