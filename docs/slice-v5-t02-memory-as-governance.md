# Slice V5 T02 — Memory-as-governance

**Status:** Done — deploy verify PASS tip `f2b8ce9` (2026-07-20)  
**Date:** 2026-07-20  
**Epic ticket:** T02  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0021-memory-as-governance.md](adr/0021-memory-as-governance.md)

## Goal

Block `/agent fix` when trajectory memory shows a **repeated failure class** on overlapping files **without new evidence**, and emit an auditable ledger event with `risk_tags: [repeated_failed_fix]`.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Deny | ≥N failed fix attempts of same `failure_class` + overlapping files, no newer evidence → fix blocked | pass (unit + CT103 smoke) |
| Allow (no history) | Empty / insufficient failure history → approve path unchanged | pass (unit) |
| Allow (new evidence) | After repeated failures, `new_evidence=true` or newer review/plan findings → allow | pass (unit) |
| Audit | Deny emits `agent.memory_governance_denied` with `repeated_failed_fix` | pass (unit + CT103 smoke) |
| AgentFacts | `agentctl agentfacts check` still passes after card re-sign | pass (CT103) |

## Design

1. On CI `verdict=failing` with collected failure evidence, upsert a selective fix memory record (`outcome=failed`, `failure_class`, files).
2. `memory_as_governance_check(repo, issue_id, file_paths)` groups failed attempts by class; threshold default **2**.
3. New evidence = memory created after the last matching failure with `machine_readable.new_evidence=true`, or a newer review/plan with findings/`evidence_refs`.
4. Hook after approval checks in `evaluate_fix_request`; deny reason starts with `memory_governance:`.
5. Append idempotent audit event on deny.

## CLI

```bash
agentctl memory governance-check --repo owner/name --issue N --files path/a,path/b
```

## Deploy verification (2026-07-20)

| Field | Value |
|-------|-------|
| Ticket ID | T02 |
| Slice doc | `docs/slice-v5-t02-memory-as-governance.md` |
| Tip SHA (expected) | `f2b8ce9` |
| Date (UTC) | 2026-07-20 |
| Operator | V5 slice coordinator |

### A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| test | pass | run #711 |
| deploy (CT103) | pass | run #712 |
| deploy-ct104 | pass | run #713 |

(Run IDs unordered by name; all three `success` for tip `f2b8ce9`.)

### B. Host tip pin

| Host | Tip SHA | Match? |
|------|---------|--------|
| CT103 (`192.168.4.62`) | `f2b8ce9` | yes |
| CT104 (`192.168.4.63`) | `f2b8ce9` | yes |

### C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok | status `degraded` (model paths); redis/state ok |
| Required compose services up | ok | control-plane running tip |
| Unexpected write-token on CT104 | absent | `CT104_NO_WRITE_TOKEN_OK` |

### D. Slice smoke

| Step | Result | Evidence |
|------|--------|----------|
| Seed 2× `lint_failure` memory + governance deny | pass | `T02_DENY_OK` |
| Audit event `agent.memory_governance_denied` | pass | `T02_AUDIT_OK` |
| `agentctl agentfacts check` | pass | ok; T02 limitation listed |

### E. Regression floor

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass |
| Publish via CT103 `publish-broker` only | pass / N/A (unchanged) |
| Risk 2 still gated | pass (approval + memory governance) |

```text
DEPLOY_VERIFY: PASS
tip: f2b8ce9
next_slice_unblocked: yes
blocker: none
```
