# Slice 5.8 + 6F.2 — Sandboxed Repair Bundle

**Status:** Approved / implementation pending  
**Date:** 2026-07-17  
**Prerequisite:** [slice-5.6a-srt-sandbox-spike.md](slice-5.6a-srt-sandbox-spike.md) (signed off), [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) (6F.1 + gate demo)  
**ADR:** [0002-srt-sandbox-backend.md](adr/0002-srt-sandbox-backend.md)  
**Plan:** Cursor plan `5.8_+_6f.2_bundle` (revised after lock/authority/verify/recovery review)

## Thesis

```text
Phase A: deployed command_registry + command_runner → SandboxBackend only (fail closed)
Phase B: durable reservation + RQ → CT104 ci_repair → mandatory SRT verify → non-force push
         → fix_ci_repair_pushed → CT103 registers 6E pending / supersedes old SHA
```

One PR, two commit groups. Demo-only (`ai-sdlc-lab/demo-app`). CT104 publish remains transitional debt (§0.7).

## Authority

| Host | Owns |
|------|------|
| CT103 | Observer lock, reservation create, RQ enqueue, ledger, pending/supersede from `repair_pushed` |
| CT104 | Lease, checkout, patch apply, closed-world gates, SRT verify (no Gitea write creds in sandbox), non-force push, durable report |

## Concurrency

```text
observer coordination lock (short)
  → create durable reservation (repo+PR+expected_sha+attempt)
  → enqueue deterministic RQ job
  → emit agent.fix_ci_repair_requested
  → release observer lock

worker claims reservation + repair lease (TTL/heartbeat)
  → execute → terminal result → release lease in finally
```

## Events

`agent.fix_ci_repair_requested|started|pushed|blocked|exhausted|stale` plus `agent.sandbox_check_failed`.  
Reasons: `sandbox_attestation_failed`, `verification_failed`, `verification_timed_out`, `scope_violation`, `remote_head_changed`, `push_rejected`, `repair_budget_exhausted`, `failure_class_not_auto`, `no_mapped_verifier`, `dispatch_failed`.

## Homelab acceptance

See plan checklist (dual observe → one job; session-bound attest; post-patch verify; dual head checks; CT103 pending idempotent; no merge).

## Out of scope

CT103 publish brokerage, full `tool_policy.v2`, non-demo repair, classifier polish.
