---
id: ADR-0005
title: Protected-default-branch policy_source_sha pin
status: proposed
date: 2026-07-19
---

# ADR-0005 — Protected-default-branch policy_source_sha pin

## Context

After CT103 publish brokerage (ADR-0004), workers still cloned policy from a branch tip and could fall back to the writable task checkout. A compromised task branch or attacker-controlled remote with the same object name could influence closed-world / tool policy.

## Decision

CT103 resolves an immutable policy identity once per job/attempt:

- `policy_source_repo`, `policy_source_remote`, `policy_source_ref`, `policy_source_sha`, `policy_schema_version`
- Ref is the project's `protected_policy_ref` tip (not PR base unless identical)
- Workers check out that SHA into a detached, separate `policy_repo` workspace
- Verify `HEAD == policy_source_sha` and remote identity; fail closed on mismatch
- Remove task-branch policy fallback
- Repair reservations carry the same pin and prepare a sibling RO policy tree

## Consequences

- Jobs cannot start without a resolvable protected-branch SHA
- Retries reuse the recorded pin; a new attempt records a new pin
- `tool_policy.v2` (PR2) must load only from this workspace

## Related

- [slice-v411-closeout.md](../slice-v411-closeout.md) PR1
- ADR-0004 CT103 publish brokerage
