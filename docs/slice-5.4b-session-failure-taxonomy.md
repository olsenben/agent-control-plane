# Slice 5.4b — Session failure / blocked taxonomy

**Status:** planned  
**Prerequisite:** [Slice 5.4a](slice-5.4-typed-sessions.md) accepted (`6f3833a`)  
**Umbrella:** [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) (PR-S2)  
**Unblocks:** 5.5 deterministic preflight (sessions need stable terminal semantics before attaching artifacts)

## Goal

Close the gap between “session lifecycle exists” (5.4a) and “session lifecycle is truthful on deny/fail paths.” Every typed command that starts (`review`, `plan`, `fix`, `repair`) must end in exactly one terminal ledger event with a **canonical `reason_code`** drawn from the V4 taxonomy — especially `session_blocked` paths that today emit only Gitea comments or domain-specific ledger events (`agent.fix_ci_repair_blocked`) without updating `agent_session.v1`.

## Problem (observed after 5.4a)

| Path | Today | Gap |
|------|-------|-----|
| `/agent review` / `plan` success | `session_finished` (`ingest_completed`) | OK |
| Enqueue failure after `begin_typed_session` | `session_failed` (`enqueue_failed`) | OK |
| Worker ingest failure | `session_failed` (`worker_failed` / `terminal_status`) | Ad-hoc codes |
| `/agent fix` policy deny (no approval, expired, hash mismatch) | Gitea `format_fix_blocked` only | **No session** — deny happens before `begin_typed_session` |
| `/agent fix` empty `allowed_files` | Gitea comment only | **No session** |
| Publish broker attestation reject | CAS `rejected`; no session terminal | **Session stays `running`** |
| CI repair dispatch blocked | `agent.fix_ci_repair_blocked` ledger only | **No `session_blocked`** on fix/repair session |
| Sandbox unavailable at dispatch | Risk-2 gate / `sandbox_unavailable` in ACI | Not mapped to session terminal |

5.4a shipped the happy path. 5.4b makes deny/fail paths auditable through the same session spine.

## Canonical taxonomy (V4 plan §5a)

Terminal **status** is one of `finished` | `failed` | `blocked`. Terminal **`reason_code`** is a separate, stable string on `agent_session.v1` and on `agent.session_finished|failed|blocked` payloads.

### Locked reason codes (5.4b minimum)

| `reason_code` | Terminal status | When |
|---------------|-----------------|------|
| `session_finished` | `finished` | Generic success when no finer code applies (prefer specific codes below) |
| `ingest_completed` | `finished` | Review/plan ingest success (existing) |
| `publish_succeeded` | `finished` | Fix/repair publish success (existing) |
| `repair_publish_succeeded` | `finished` | Repair publish success (existing) |
| `session_failed` | `failed` | Generic worker/operator failure |
| `enqueue_failed` | `failed` | Redis enqueue failure after session start (existing) |
| `worker_failed` | `failed` | Worker terminal failure on ingest |
| `publish_failed` | `failed` | Publish/verification terminal failure |
| `session_blocked` | `blocked` | Generic policy/dispatch block |
| `policy_denied` | `blocked` | Tool/command policy deny, repair allowlist deny, diff-gate deny |
| `human_approval_required` | `blocked` | Fix attempted without valid approval / empty scope / approval state conflict |
| `sandbox_unavailable` | `blocked` | SRT probe fail, attestation not strong, sandbox gate at dispatch or publish |
| `verification_missing` | `blocked` | Command kind requires verification evidence that is absent (stub for 5.6; wire read path only) |
| `context_overflow` | `blocked` | Context/packet exceeds budget (stub mapper; full enforcement in 5.5+) |

**Rule:** `reason_code` values are snake_case, stable, and drawn from the table above or an explicit extension list in code (`SessionTerminalReason` enum). Upstream subsystem codes (e.g. `repository_not_allowlisted`, `sandbox_attestation_missing`) map through a single module — callers do not invent parallel strings at finalize sites.

### Status vs event type

| `status` | Ledger event |
|----------|--------------|
| `finished` | `agent.session_finished` |
| `failed` | `agent.session_failed` |
| `blocked` | `agent.session_blocked` |

## Implementation

### 1. `session_terminal.py` (new)

Central module under `src/agent_control/session/`:

- `SessionTerminalReason` — `StrEnum` of locked codes above
- `TerminalDecision` — `status` + `reason_code` + optional `reason` (human detail)
- `map_fix_policy_block(reason: str) -> TerminalDecision` — approval missing → `human_approval_required`; plan resolution errors → `policy_denied`
- `map_publish_reject(reason_codes: list[str]) -> TerminalDecision` — attestation/sandbox codes → `sandbox_unavailable`; else `policy_denied`
- `map_repair_dispatch_block(reason_codes: list[str]) -> TerminalDecision` — allowlist/class/publish flags → `policy_denied` or `sandbox_unavailable`
- `finalize_with_decision(state_root, session, run_id, decision)` — thin wrapper over `finalize_session`

Validate `reason_code` at finalize time (reject unknown codes in strict mode / tests).

### 2. Fix handler — session on deny

**File:** `src/agent_control/approval/handlers.py`

When `/agent fix` is blocked (`policy_decision == "blocked"` or empty `allowed_files`):

1. `begin_typed_session` with `command_kind="fix"` (subject = issue, `invoked_by` = comment author)
2. `finalize_with_decision(..., blocked, mapped reason_code)`
3. Keep existing Gitea comments unchanged

Session must exist even when enqueue never runs — matches terminal-ownership table in 5.4a (“Policy denial → Dispatch/approval → `blocked`”).

### 3. Publish broker — terminal on reject

**File:** `src/agent_control/publish/broker.py`

On attestation gate / bundle invalid / binding missing / publish decision deny:

- Call `handle_publish_session_terminal` (or `finalize_with_decision`) with mapped `reason_code`
- Success path already calls `handle_publish_session_terminal` — extend reject paths symmetrically

Applies to both `broker_publish_fix` and `broker_publish_repair`.

### 4. CI observe — repair block → session

**File:** `src/agent_control/ci/observe.py`

When `dispatch.get("blocked")` and `append_fix_ci_repair_blocked` fires:

- Load fix session by `pending.fix_run_id` (or repair session if created)
- `finalize_with_decision(..., blocked, map_repair_dispatch_block(reason_codes))`

Do not double-terminal when `reservation_exists` (existing dedupe).

### 5. Model / CLI

- Optional: constrain `terminal_reason_code` on `AgentSession` via validator against enum (warn-only in prod first if needed)
- `agentctl session show --json` already surfaces `terminal_reason_code` — no CLI change required

### 6. Tests

**New:** `tests/test_session_terminal_taxonomy.py`

| Case | Assert |
|------|--------|
| Fix deny without approval | `status=blocked`, `reason_code=human_approval_required`, one `agent.session_blocked` |
| Fix empty `allowed_files` | `human_approval_required` or `policy_denied` (locked in test) |
| Publish attestation reject | `sandbox_unavailable`, session terminal, no `session_finished` |
| Repair dispatch allowlist deny | `policy_denied` + existing `fix_ci_repair_blocked` |
| Mapper unit tests | Each upstream code maps to expected canonical code |
| Idempotent re-finalize | Same terminal + code → no second ledger event |

Extend `tests/test_typed_sessions.py` only if shared helpers move.

## Homelab acceptance

Prerequisite: CT103 + CT104 at tip containing 5.4b code; CI green.

| Check | Procedure | Pass |
|-------|-----------|------|
| Tip deploy | `scripts/_validate_tip_deploy.sh` | CT103 `readyz`; CT103/CT104 same commit |
| Positive regression | Re-run fake `/agent review` on demo-app#2 | Still `session_finished` / `ingest_completed` |
| Policy deny | `/agent fix` on issue without `/agent approve` | `sess-…` with `blocked` + `human_approval_required`; ledger `agent.session_blocked` |
| Sandbox deny (preferred) | Publish or repair with stripped/invalid sandbox attestation on demo path | `blocked` + `sandbox_unavailable` |
| CLI | `agentctl session show --session-id sess-… --json` | `terminal_reason_code` matches table |

Record session IDs and commit SHA in this doc on acceptance (mirror 5.4a table).

## Acceptance criteria

1. Every deny path in scope creates at most one terminal session event with a canonical `reason_code`
2. No success terminal (`session_finished`) on intentional deny scenarios
3. Existing 5.4a happy path and mismatch fail-closed behavior unchanged
4. Unit tests cover mappers + at least one integration path per command kind (`fix` deny, publish reject)
5. Homelab: one intentional `session_blocked` demonstrated and logged below

## Out of scope (5.5+)

- `memory_preflight.v1` attachment
- Full `verification_missing` enforcement gate (5.6)
- `context_overflow` enforcement (5.5 preflight)
- Gitea terminal ack comments
- 2070 invocation

## Related

- [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md) — 5.4a spine
- [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) — bundle order
- [adr/0010-ct103-authoritative-typed-sessions.md](adr/0010-ct103-authoritative-typed-sessions.md)
- [slice-5.6a-srt-sandbox-spike.md](slice-5.6a-srt-sandbox-spike.md) — sandbox deny signals
- [POLICY_GATES.md](POLICY_GATES.md) — approval / elevated approval

## Suggested implementation prompt

```text
Implement Slice 5.4b session failure/blocked taxonomy on CT103.

- Add session_terminal.py with SessionTerminalReason enum and upstream mappers
- On /agent fix policy deny and empty allowed_files: begin_typed_session then finalize blocked
- On publish broker reject paths: handle_publish_session_terminal with mapped reason_code
- On CI repair dispatch blocked: terminal the fix/repair session (respect reservation_exists dedupe)
- Tests: test_session_terminal_taxonomy.py + homelab script for fix-without-approve
- Do not add preflight, verification gate, or Gitea ack comments
- Doc: tick acceptance table in docs/slice-5.4b-session-failure-taxonomy.md after homelab proof
```
