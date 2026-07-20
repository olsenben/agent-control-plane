# Parallel lanes — retired (V4 epic closed)

Wave 1–2 lane worktrees were removed after T08/T11/T09/T13 closed (2026-07-20). Tip pin authority remains **main** only.

| Former lane | Former branch | Status |
|-------------|---------------|--------|
| Graph T05–T07 | `epic/lane-graph-t05-t07` | merged; worktree removed |
| Identity T10 | `epic/lane-identity-t10` | merged; worktree removed |
| Loop T08 | `epic/lane-t08-qwen-loop` | merged; worktree removed |
| MCP T11 | `epic/lane-t11-mcp` | merged; worktree removed |
| Deploy-verify owner | `main` | active (`agent-control-plane`) |

## Current policy

```text
No active dual lanes.
New epic work: use docs/handoff/boss-ledger-v5.md
Optional T12 (controller bake-off): still Deferred unless explicitly reopened
```

Do not recreate worktrees unless a future epic opens disjoint lanes again. Only one **deploy-verify owner** may pin CT103/CT104.

Note: empty leftover folders under `ai-sdlc-lab/agent-control-plane-lane-*` may remain if Windows/Cursor still holds a handle; git worktrees and remote epic branches are already gone. Delete those folders when idle.
