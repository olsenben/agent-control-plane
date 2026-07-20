# Slice V5 T01 — AgentFacts-lite

**Status:** Done — deploy verify PASS tip `bdbdc99` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T01  
**Deps:** —  
**ADR:** [0020-agentfacts-lite-integrity.md](adr/0020-agentfacts-lite-integrity.md)

## Goal

Ship signed capability / limitation manifests so the machine card (`agent-card.json`) and human card (`docs/AGENT_CARD.md`) stay in sync, and unsigned or stale manifests fail a documented check.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Sync | `agentctl agentfacts check` ok when MD ↔ JSON command/risk/approval align | pass |
| Sync fail | Divergent risk/approval → non-zero exit + `sync:` errors | pass (unit) |
| Unsigned | Missing `agent-facts.json` or missing `integrity` → fail | pass (CT103 live) |
| Stale | Card files change without re-sign → `stale:` source hash errors | pass (unit) |
| Digest | Tampered payload → digest mismatch | pass (unit) |
| Optional HMAC | With `AGENTFACTS_SIGNING_SECRET` + `--require-hmac` | pass (unit) |

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

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T01 |
| Slice doc | `docs/slice-v5-t01-agentfacts-lite.md` |
| Tip SHA (expected) | `bdbdc99` |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test | pass | run #705 |
| deploy (CT103) | pass | run #706 |
| deploy-ct104 | pass | run #707 |

(Run IDs unordered by name; all three `success` for tip `bdbdc99`.)

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `bdbdc99` | yes |
| CT104 (`192.168.4.63`) | `bdbdc99` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model paths); redis/state ok |
| Required compose services up | ok | control-plane, publish-broker, redis, worker-state |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| `agentctl agentfacts check --repo-root /app` | pass | sync ok; digest present |
| Unsigned negative (no manifest) | pass | `UNSIGNED_FAIL_OK` |
| Image COPY of cards | pass | Dockerfile ships cards into `/app` |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | pass / N/A (unchanged) |
| Risk 2 still gated | N/A (not exercised) |

```text
DEPLOY_VERIFY: PASS
tip: bdbdc99
next_slice_unblocked: yes
blocker: none
```

## Note

Tip `04fad85` shipped the feature but failed in-container check until `bdbdc99` COPY'd card files into the image.
