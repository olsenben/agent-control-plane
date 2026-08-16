# Slice 5.8 + 6F.2 — Sandboxed Repair Bundle

**Status:** Homelab signed off 2026-07-18 (demo-app)  
**Date:** 2026-07-17 (acceptance 2026-07-18)  
**Prerequisite:** [slice-5.6a-srt-sandbox-spike.md](slice-5.6a-srt-sandbox-spike.md) (signed off), [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) (6F.1 + gate demo)  
**ADR:** [0002-srt-sandbox-backend.md](adr/0002-srt-sandbox-backend.md), [0003-ct104-bwrap-docker-caps.md](adr/0003-ct104-bwrap-docker-caps.md)  
**Plan:** Cursor plan `5.8_+_6f.2_bundle` (revised after lock/authority/verify/recovery review)

## Thesis

```text
Phase A: deployed command_registry + command_runner → SandboxBackend only (fail closed)
Phase B (historical 6F.2 path): durable reservation + RQ → CT104 ci_repair → mandatory SRT verify → non-force push
         → fix_ci_repair_pushed → CT103 registers 6E pending / supersedes old SHA
```

Demo-only (`ai-sdlc-lab/demo-app`). At this slice's 2026-07-18 acceptance, CT104 publication was explicitly transitional debt. Slice 6D.2 subsequently retired that debt: CT104 now emits immutable patch bundles and CT103 is the sole Gitea mutation authority.

## Authority

| Host | Owns |
|------|------|
| CT103 | Observer lock, reservation create, RQ enqueue, ledger, pending/supersede from `repair_pushed` |
| CT104 (historical 6F.2 acceptance) | Lease, checkout, patch apply, closed-world gates, SRT verify (no Gitea write creds in sandbox), non-force push, durable report |

Current authority is defined by [Slice 6D.2](slice-6d2-ct103-publish-brokerage.md) and [ADR-0004](adr/0004-ct103-publish-brokerage.md): CT104 stops at immutable patch-bundle production; CT103 independently validates and publishes.

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

## Homelab acceptance (`demo-app` 2026-07-18)

| Check | Result |
|-------|--------|
| Dual observe → one reservation/job | Pass (reconcile on failing `4ebaab0…`) |
| Worker checkout `expected_sha` | Pass |
| Strong SRT session + post-patch verify | Pass (after ADR-0003 caps + runtime mounts) |
| Closed-world / allowed_files | Pass (patch outside worktree) |
| Non-force push; capture new SHA | Pass → `16886456261c6cb69a2cf37f02a0ea58dc440fac` |
| CT103 pending re-point | Pass (pending SHA = new head) |
| Gitea CI on repaired head | Pass (push + PR statuses success) |
| `main` unchanged / no merge | Pass |

Fixture: issue #4 / PR #5; intentional-fail removed by demo heuristic; ACP runtime fix commit `d3d3ea2`.

## Out of scope

At the time of this slice: CT103 publish brokerage, full `tool_policy.v2`, non-demo repair, classifier polish, model-authored repair proposals. CT103 publish brokerage was completed in Slice 6D.2.
