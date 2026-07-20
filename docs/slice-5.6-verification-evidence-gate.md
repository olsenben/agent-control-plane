# Slice 5.6 — Verification Evidence Gate

**Status:** Implemented — deploy verification pending  
**Date:** 2026-07-20  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) PR-S4  
**Builds on:** [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md), [slice-5.5-deterministic-preflight.md](slice-5.5-deterministic-preflight.md), [slice-6e-ct102-ci-truth-loop.md](slice-6e-ct102-ci-truth-loop.md)  
**ADR:** [0012-session-verification-evidence-gate.md](adr/0012-session-verification-evidence-gate.md)

## Goal

Sessions cannot claim verified from model prose. CT103 emits machine-recorded `agent.verification_*` events. Fix/repair defer `session_finished` until a 6E CI terminal verdict (or expire → `verification_missing`).

## Locked policy

| Command | On success path | Terminal |
|---------|-----------------|----------|
| `review` / `plan` | Emit `agent.verification_missing` then `session_finished` / `ingest_completed` | Ingest |
| `fix` / `repair` | After publish: stay `running` + `agent.verification_requested` | CI verdict |

| 6E verdict | Verification event | Session terminal |
|------------|--------------------|------------------|
| `verified` | `agent.verification_passed` | `finished` / `ci_verified` or `repair_ci_verified` |
| `failing` (no repair) | `agent.verification_failed` | `failed` / `verification_failed` |
| `failing` + repair requested | `agent.verification_failed` | stay `running` |
| `expired` | `agent.verification_missing` | `blocked` / `verification_missing` |
| `superseded` | (none) | stay `running` until new SHA request |

## Artifacts / events

| Artifact | Path |
|----------|------|
| Claim | `sessions/{session_id}/verification_claim.json` (`verification_claim.v1`) |
| Session ref | `AgentSession.verification` |

Events: `agent.verification_requested|passed|failed|missing`.

## CLI

```text
agentctl session show --session-id sess-… --repo owner/repo [--json]
```

Includes `verification_summary` when present.

## Tests

`tests/test_verification_gate_56.py` — request, review missing, CI verified/failing/expired coupling.

## Follow-on

- **5.7** — selective writeback from session trace (consumes verification refs)
- Adequacy profile for agent-authored tests (plan item 7)
