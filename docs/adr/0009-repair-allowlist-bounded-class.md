---
id: ADR-0009
title: Central repair allowlist and bounded ACP lint class
status: proposed
date: 2026-07-19
---

# ADR-0009 — Central repair allowlist and bounded ACP lint class

## Context

Automatic CI repair previously gated on flags, evidence, and sandbox attestation
but not on an explicit per-repository allowlist. Demo intentional-fail heuristics
must not apply to `ai-sdlc-lab/agent-control-plane`.

## Decision

1. Single decision function `decide_repair_repository` returns
   `allowed`, `reason_code`, `normalized_repository`, `matched_allowlist_entry`,
   `repair_class`, `effective_policy_hash`.
2. `FIX_CI_REPAIR_ALLOWED_REPOS`: comma-separated exact `owner/repo` only;
   **no wildcards**; invalid entries fail Settings startup; **empty = deny all**.
3. `FIX_CI_REPAIR_ALLOWED_CLASSES` defaults to `lint_failure` (ruff family).
4. Path envelope rejects trust-boundary paths (`.agent/**`, workflows, sandbox,
   publish/broker/policy_loader/command_runner, compose, `.env*`, ADRs, …).
5. Intentional-fail stub removal is hard-gated to `ai-sdlc-lab/demo-app` only.
6. `FIX_CI_REPAIR_PUBLISH_ENABLED` defaults false (repair-without-publish stage).
7. Flags remain off until staged ops: observe → repair-no-publish → publish.

## Consequences

- Demo repair tests must set allowlist + classes explicitly.
- Production ACP enablement is a deliberate allowlist/class/publish flip, not
  implied by `FIX_CI_REPAIR_ENABLED` alone.

## Related

- ADR-0004 (brokerage), ADR-0006 (tool_policy.v2), ADR-0008 (CT102)
- V4.1.1 closeout PR4 / [slice-v411-closeout.md](../slice-v411-closeout.md)
