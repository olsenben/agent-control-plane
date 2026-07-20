# Slice V5 T02 — Memory-as-governance

**Status:** In Progress  
**Date:** 2026-07-20  
**Epic ticket:** T02  
**Deps:** T01 Done (`bdbdc99`)  
**ADR:** [0021-memory-as-governance.md](adr/0021-memory-as-governance.md)

## Goal

Block `/agent fix` when trajectory memory shows a **repeated failure class** on overlapping files **without new evidence**, and emit an auditable ledger event with `risk_tags: [repeated_failed_fix]`.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Deny | ≥N failed fix attempts of same `failure_class` + overlapping files, no newer evidence → fix blocked | pending |
| Allow (no history) | Empty / insufficient failure history → approve path unchanged | pending |
| Allow (new evidence) | After repeated failures, `new_evidence=true` or newer review/plan findings → allow | pending |
| Audit | Deny emits `agent.memory_governance_denied` with `repeated_failed_fix` | pending |
| AgentFacts | `agentctl agentfacts check` still passes after card re-sign | pending |

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

## Deploy smoke (minimum)

Fix path deny when memory says repeated failure class without new evidence; audit event emitted.
