# Parallel lanes — wave 2 (T08 ∥ T11)

Disjoint worktrees/branches. **One deploy-verify owner** (boss) serializes CT103/CT104 tip pins.

| Lane | Branch | Worktree | Owns | Must not |
|------|--------|----------|------|----------|
| **Loop** | `epic/lane-t08-qwen-loop` | `…-lane-t08` | **T08** Recursive Qwen loop (evidence + CI retries) | MCP server surface; Risk-2 allowlist expand (T09); tip-pin/deploy |
| **MCP** | `epic/lane-t11-mcp` | `…-lane-t11` | **T11** Read-only MCP graph/memory | Qwen retry loop; repair/publish; tip-pin/deploy |
| **Deploy-verify owner** | `main` | `agent-control-plane` | Merge order; tip pins; `DEPLOY_VERIFY`; ledger | Parallel tip races |

Base tip: `8523a0e` (T10 signoff on main).

## Order

```text
Now:   T08 ∥ T11   (PR-only until owner merges)
Then:  T09 alone   (Risk-2 — no parallel enablement track)
Last:  T13         (after T08 Done)
Defer: T12         (controller bake-off — Deferred)
```

Prefer merge **T08** first when both ready (critical path). Merge **T11** after T08 tip green (or same wave if no file thrash — owner decides). Never auto-deploy from lane agents.

## File / concern split

| Area | T08 | T11 |
|------|-----|-----|
| Recursive Qwen / CI retry / evidence-selected context | yes | no |
| `recursive_context` worker (consume results only) | yes | read-only via MCP |
| New MCP server / `docs/mcp.md` | no | yes |
| Graph/memory **write** paths | no | **forbidden** |
| Repair allowlist / 6F.2 (T09) | no | no |
| `boss-ledger.md` | propose only | propose only |
| SSH tip pin | **owner only** | **forbidden** |

## Agent return

```text
lane: t08 | t11
ticket_id: T08 | T11
branch: epic/…
pr_url: … | pending
stopped_reason: ticket_ready_for_merge | blocker | context_handoff
blocker: none | <one line>
```
