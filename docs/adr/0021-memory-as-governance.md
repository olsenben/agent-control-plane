---
id: ADR-0021
title: Memory-as-governance blocks repeated failed fix classes
status: proposed
date: 2026-07-20
---

# ADR-0021: Memory-as-governance blocks repeated failed fix classes

## Context

Risk 2 `/agent fix` already requires human approval, but repeated identical CI failure classes on the same issue/files waste cycles and amplify thrashing. THREAT_MODEL tags this as `repeated_failed_fix`. POLICY_GATES listed memory-as-governance as a later gate after approval.

## Decision

1. On CI `verdict=failing` with collected failure evidence, upsert a selective fix memory record (`outcome=failed`, `failure_class`, files) — distinct from 6E.2 `ci_verified` writeback.
2. After approval checks in `evaluate_fix_request`, run `memory_as_governance_check`. Deny when ≥N (default 2) overlapping failed attempts share a failure class and no newer evidence exists.
3. New evidence unlocks retry: `machine_readable.new_evidence=true`, or a newer review/plan with findings/`evidence_refs`.
4. Denies emit idempotent `agent.memory_governance_denied` with `risk_tags: [repeated_failed_fix]`.
5. AgentFacts-lite check is unchanged; re-sign cards if limitations text changes.

## Consequences

- Positive: fail-closed thrash brake with auditable ledger signal; operators can unlock via explicit new evidence.
- Negative: threshold and evidence rules are heuristic; false denies require a review/plan or new_evidence marker.
- Follow-up: surface deny reason in Gitea comments (already via fix blocked path); optional operator CLI already ships as `agentctl memory governance-check`.
