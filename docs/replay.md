# Review replay console

V5 T03 operator console: reconstruct one finished `/agent review` session from durable CT103 artifacts.

## Command

```bash
agentctl replay review --repo owner/name --session-id sess-…
agentctl replay review --repo owner/name --run-id run-… --text
```

Default output is JSON (`review_replay.v1`). Use `--text` for a compact stage summary. Use `--allow-unfinished` only for diagnostics.

## Stage spine

| Stage | Durable sources |
|-------|-----------------|
| **issue** | `agent_session.v1` (subject, invoker, head/input SHAs) |
| **context** | `memory_preflight.json`, `context_packet.json`, verification claim if present |
| **model** | `agent.run_completed` payload + memory `source_model` / `source_engine` |
| **policy** | `policy_source_sha`, risk tags/level, policy/approval/block ledger events |
| **memory** | SQLite trajectory record for the run/session + `agent.memory_*` events |

`complete=true` when every stage reports `present=true`.

## Notes

- Read-only: does not mutate ledger, sessions, or memory.
- Requires a **finished** review session by default (deploy smoke).
- Parallel V5 T04 (architecture drift) is a separate lane; this console does not compare ADR graph edges.
