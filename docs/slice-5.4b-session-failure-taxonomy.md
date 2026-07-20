# Slice 5.4b — Session failure / blocked taxonomy

**Status:** Implemented (pending homelab sign-off)  
**Date:** 2026-07-20  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md)  
**Builds on:** [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md)

## Goal

Canonical terminal reason codes with strict status/reason validation. Policy and sandbox gates emit `session_blocked`; operational failures emit `session_failed`. CT103 is the authoritative classifier and ledger emitter.

## Semantic rule

| Terminal | Meaning |
|----------|---------|
| `blocked` | System deliberately refused to continue (policy / safety gate) |
| `failed` | Work was attempted but could not complete |
| `finished` | Intended lifecycle completed for that command owner |

## Canonical reasons (`SessionTerminalReason`)

| Status | Codes |
|--------|-------|
| `finished` | `ingest_completed`, `publish_succeeded`, `repair_publish_succeeded` |
| `failed` | `enqueue_failed`, `worker_failed`, `publish_failed`, `session_failed` |
| `blocked` | `policy_denied`, `human_approval_required`, `sandbox_unavailable`, `session_blocked` |
| reserved | `verification_missing`, `context_overflow` (5.5 / 5.6) |

Emitter validates every `(status, reason_code)` pair against `ALLOWED_REASONS_BY_STATUS`. Unknown domain codes normalize to canonical fallbacks; originals are stored in structured `terminal_reason` JSON (`domain_reasons`).

## Ingest ownership

| Command | Worker outcome | Ingest terminal |
|---------|----------------|-----------------|
| review/plan | success | `finished` / `ingest_completed` |
| review/plan | `policy_decision=deny` | `blocked` / `policy_denied` |
| review/plan | operational failure | `failed` / `worker_failed` |
| fix/repair | publish candidate | `running` (broker owns success) |
| fix/repair | policy deny | `blocked` / `policy_denied` |
| fix/repair | worker failure / no bundle | `failed` / `worker_failed` |

**Publish candidate** (`is_publish_candidate`): `patch-bundle.v1` + `patch_bundle_ready` + `bundle_id` (+ remote publish enabled for fix).

## Policy vocabulary boundary

| Layer | Values | Maps to |
|-------|--------|---------|
| `FixEvaluation.policy_decision` | `blocked` / `approved` | pre-enqueue block reasons |
| `AgentRunCompletedEvent.policy_decision` | `allow` / `deny` | ingest `blocked` when `deny` |

## Broker reject matrix

| Outcome | Status | Reason |
|---------|--------|--------|
| Attestation missing / sandbox unavailable | `blocked` | `sandbox_unavailable` |
| Approval / policy gate | `blocked` | `policy_denied` |
| Stale base after work | `failed` | `publish_failed` |
| Push / PR / corrupt artifact | `failed` | `publish_failed` |
| Success | `finished` | `publish_succeeded` / `repair_publish_succeeded` |

## Pre-enqueue fix block

`/agent fix` without approval creates an idempotent blocked session (`by_blocked_request` index). Replay returns the same `session_id` without duplicate terminal events.

| Condition | Reason |
|-----------|--------|
| No valid approval | `human_approval_required` |
| Expired / hash mismatch / empty scope / consumed | `policy_denied` |

## Enqueue dedupe

`EnqueueResult`: `enqueued` | `deduplicated` | `failed`. Dedupe reuses existing session; only `failed` terminalizes with `enqueue_failed`.

## Homelab acceptance

### A. Early deny — no approval

1. demo-app issue with plan, no `/agent approve`
2. Post `/agent fix <target>`
3. Verify: `status=blocked`, `terminal_reason_code=human_approval_required`
4. Ledger: exactly one `session_started`, `subject_context_resolved`, `session_blocked`; zero `session_finished` / `session_failed`
5. No worker enqueue; no publish

### B. Late deny — attestation boundary

1. Fix run completes with bundle
2. Broker denies (missing attestation)
3. Verify: `session_blocked` + `sandbox_unavailable`; `domain_reasons` retains specific attestation code
4. No Gitea mutation

## Tests

`tests/test_session_taxonomy_54b.py`, extended `tests/test_typed_sessions.py`, `tests/test_fix_enqueue_6b.py`

## Code

- `src/agent_control/session/reasons.py`
- `src/agent_control/session/publish_candidate.py`
- `src/agent_control/session/lifecycle.py`
- `src/agent_control/queue.py` (`EnqueueResult`)
- `src/agent_control/approval/handlers.py`
- `src/agent_control/publish/broker.py`
