# Slice V5 T01 — AgentFacts-lite

**Status:** In Progress — awaiting DEPLOY_VERIFY  
**Date:** 2026-07-20  
**Epic ticket:** T01  
**Deps:** —  
**ADR:** [0020-agentfacts-lite-integrity.md](adr/0020-agentfacts-lite-integrity.md)

## Goal

Ship signed capability / limitation manifests so the machine card (`agent-card.json`) and human card (`docs/AGENT_CARD.md`) stay in sync, and unsigned or stale manifests fail a documented check.

## Acceptance

| Check | Expected |
|-------|----------|
| Sync | `agentctl agentfacts check` ok when MD ↔ JSON command/risk/approval align |
| Sync fail | Divergent risk/approval → non-zero exit + `sync:` errors |
| Unsigned | Missing `agent-facts.json` or missing `integrity` → fail |
| Stale | Card files change without re-sign → `stale:` source hash errors |
| Digest | Tampered payload → digest mismatch |
| Optional HMAC | With `AGENTFACTS_SIGNING_SECRET` + `--require-hmac`, invalid/missing HMAC fails |

## Artifacts

| Path | Role |
|------|------|
| `agent-facts.json` | Committed AgentFacts-lite manifest |
| `agent-card.json` | Machine capability card |
| `docs/AGENT_CARD.md` | Human transparency card |
| `src/agent_control/agentfacts/` | sync / sign / check |
| `src/agent_control/schemas/agent_facts.schema.json` | JSON Schema |

## CLI

```bash
agentctl agentfacts check --repo-root .
agentctl agentfacts sign --repo-root .
agentctl agentfacts show --repo-root .
```

Re-sign after editing either card file. Optional: set `AGENTFACTS_SIGNING_SECRET` and use `--require-hmac`.

## Deploy smoke (ledger)

1. CT103 tip pin matches tip SHA
2. `docker compose exec -T control-plane agentctl agentfacts check --repo-root /app </dev/null` → ok
3. Negative (documented): strip integrity or mutate card → check fails

## Deploy verification

_(fill after CT103/CT104 pin)_
