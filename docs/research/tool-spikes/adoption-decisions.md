# Adoption decisions

| Tool | Status | Notes |
|------|--------|-------|
| FastAPI | adopt | Webhook guard and control API |
| Redis/RQ | adopt | MVP job queue |
| pydantic-settings | adopt | Typed config |
| GitIngest | adapter | Context baseline, not canonical state |
| Ray | defer | Two-GPU lab uses RQ first |
| OpenHands | spike | Sandbox reference |
| MCP | defer | After static state works |

No dependency may bypass webhook guard, reducer, policy gates, or closed-world diff checks.
