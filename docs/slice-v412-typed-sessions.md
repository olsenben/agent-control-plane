# V4.1.2 Bundle — Typed Sessions → Recursive Context (umbrella)

**Status:** Active — 5.4a **done**; next 5.4b / 5.5  
**Date:** 2026-07-19  
**Plan source:** `gitea_agentic_sdlc_cursor_step_plan_v4.md` (§0.2a, §5a, §0.6, DoD §Recursive context, impl order 5.4–5.7 / 8a–8d)  
**Prerequisite:** V4.1.1 closeout signed ([slice-v411-closeout.md](slice-v411-closeout.md)) — **2026-07-19**  
**Excluded from first PRs:** Recurrent/SSM bake-off (8d), mandatory 2070 on every task, AgentFacts / MCP graph server

## Thesis

V4.1.2 is **not** a V5 rewrite. It clarifies that the 2070 is a **conditional RLM-style recursive context controller** (deterministic CT103 preflight first; bounded exploration only when needed). Typed agent sessions (5.4) are the durable spine that makes preflight, verification claims, and selective writeback auditable.

## Plan-doc deltas vs live status (applied 2026-07-19)

Stale V4 plan / AGENT_CARD “next” pointers were patched in the Phase A docs-sync commit:

| Location | Was | Now |
|----------|-----|-----|
| § Implementation status (~L112) | Immediate next: V4.1.1 brokerage | Immediate next: **5.4 typed sessions** → 5.5–5.7 / V4.1.2 |
| § Revised milestone (~L834) | V4.1.1 `[next]` | V4.1.1 **`[done]`** (2026-07-19); After V4.1.1 → 5.4 **[next]** |
| Impl order (~L4625) | V4.1.1 `[next]` + open tool_policy / brokerage bullets | V4.1.1 done; tool_policy.v2 + brokerage + CT102 split landed |
| V4.1 bridge (~L832) | `[in progress]` undifferentiated | Split: sandbox/attestation **done**; sessions/preflight/writeback **open** |
| AGENT_CARD Last verified | V4.1.1 closeout in progress | Closeout **done** 2026-07-19; next row for 5.4 / V4.1.2 |

**Naming trap:** Homelab **Slice 6E** = CT102 CI truth. Plan § “Slice 6E — deterministic preflight…” is the **V4.1 memory lane** — use **5.5 / 5.7** names in new docs (plan already has a naming note).

## What already exists (do not rebuild)

| Asset | Role | Gap vs 5.4 DoD |
|-------|------|----------------|
| CT104 `session_events.jsonl` + `SessionEventType` | Worker-local trajectory | Not CT103 ledger; names ≠ `agent.session_*` |
| CT103 `append_event` ledger | Approval + CI + ingest | Missing session lifecycle event types |
| Dual attestation / executor lifecycle | V4.1.1 Risk-2 executor events | Overlaps §5a executor list; keep separate from session spine |
| 6E.2 `memory_record` on `ci_verified` | CI-gated fix memory | Not session-trace selective writeback (5.7) |
| `session_id` on jobs | Often equals `run_id` | Need stable session identity spanning retries / multi-job commands |

## Locked decisions (from V4.1.2 §0.2a)

1. **RLM** = recursive inference harness, not “recurrent neural net.”
2. Deterministic CT103 preflight **always** before optional 2070.
3. 2070 never authors canonical state, graph truth, policy, or verification.
4. Recursion is bounded, read-only, evidence-triggered; no new evidence → no more iterations.
5. Verification claims are **scoped** (CI truth for checks run, not universal correctness).

## Dependency order

```text
5.4 Typed session spine (CT103)
  → 5.5 Deterministic context preflight (+ stub recursive_context_required)
    → 5.6 Verification evidence gate (session-scoped claims)
      → 5.7 Selective writeback from session trace
        → 8a Orbit-style graph edges (incremental)
          → 8b Preflight uses graph coverage
            → 8c Conditional recursive context worker (2070)
              → 8d Controller bake-off (optional; not gate for 5.4–5.7)
```

## Units (independently reviewable)

### PR-S0 — Docs sync

- Patch stale V4 plan / AGENT_CARD “next” pointers.
- Add this umbrella + link from `architecture.md` (already points at V4.1.2 / sessions).

### PR-S1 — Slice 5.4a: Session record + ledger events (CT103)

**Status:** **Done** — tip `dab1e89`; fake review `sess-206dce2b…` / `run-76d29fc7…` on demo-app#2 (2026-07-20). See [slice-5.4-typed-sessions.md](slice-5.4-typed-sessions.md).

**Goal:** Every `/agent review|plan|fix|repair` creates a typed **AgentSession** and emits append-only `agent.session_*` events on the CT103 ledger.

**Label:** 5.4a CT103-authoritative typed sessions (shared job schema + CT104 echo; durable store/ledger remain CT103-owned).

**Session identity (locked):**

- A user-issued `/agent review|plan|fix|repair` creates a **new** session.
- Retry, worker rerun, publish continuation, or automatic repair caused by that command stays in the **same** session and appends another `run_id`.
- A separately issued `/agent repair` creates a **new** session even if it references an earlier failure.
- Each `run_id` belongs to exactly one session; a session may contain one or more run IDs.
- `session_id` is always distinct from `run_id` at creation (`sess-…` vs `run-…`).

**Terminal ownership (one success owner per command):**

| Command | Successful terminal owner |
|---------|---------------------------|
| review | Results ingest after validated result persistence |
| plan | Results ingest after validated plan persistence |
| fix | Publish/verification terminal — **not** initial worker ingest |
| repair | Repair publish/verification terminal |
| Dispatch/enqueue failure | Dispatch path → `failed` |
| Policy denial | Dispatch/approval path → `blocked` |

**Deliverables:**

- Models: `agent_session.v1` (session_id, run_id(s), command_kind, risk_level, repo, issue/PR, head_sha, input_state_sha, status, correlation_id, risk_tags, acting_identity/invoked_by).
- Storage: `agent-state/projects/{owner}/{repo}/sessions/{session_id}.json` (+ index by run_id).
- Events (minimum viable spine):  
  `agent.session_started` → `agent.subject_context_resolved` → … → `agent.session_finished` | `agent.session_failed` | `agent.session_blocked`.
- CT103 derives correlation fields; worker may contribute only allowlisted fields. Worker `session_id`/`run_id` mismatch → fail closed.
- Wire start at CT103 dispatch (persist before enqueue); finalize per terminal-ownership table.
- CLI: `agentctl session show` / `session list --repo` with `--json`.
- Tests: create → append → terminal; idempotent restart; mismatch fail-closed; enqueue-failure finalization.

**Non-goals:** Gitea started-ack comments (deferred with dual-identity); 2070 calls; changing CI memory path; 5.4b taxonomy expansion.

**Acceptance:** One fake `/agent review` on demo-app leaves a durable `agent_session.v1` + ordered ledger spine ending in exactly one `session_finished`; mismatch result rejected.

### PR-S2 — Slice 5.4b: Failure / blocked taxonomy

- Terminal reasons: `session_failed`, `session_blocked`, `sandbox_unavailable`, `verification_missing`, `context_overflow`, `policy_denied`, `human_approval_required`.
- Ensure Risk-2 sandbox deny and policy deny set blocked/failed consistently with existing SRT / tool_policy paths.
- Homelab: one intentional policy-deny or sandbox-unavailable path shows `session_blocked` (not success).

### PR-S3 — Slice 5.5a: Deterministic context preflight (no 2070 yet)

- CT103 `memory_preflight.v1` at exact source SHA: events, verified memory, ADR facts, graph queries already available, CI evidence pointers.
- Always set `recursive_context_required: false|true` + `invocation_reasons[]` (heuristic thresholds; 2070 invoke deferred).
- Attach preflight artifact to session; emit `agent.memory_preflight_created` / `agent.context_packet_created`.
- Small-task path: review/plan proceeds with deterministic packet only.

**Acceptance:** Plan/review run records preflight JSON; trivial demo task stays `recursive_context_required=false`.

### PR-S4 — Slice 5.6: Verification evidence gate (session-scoped)

- Session cannot claim verified from model prose alone.
- Emit `agent.verification_requested|passed|failed|missing`.
- Integrate with existing 6E pending/verdict where command is fix/repair; review/plan use adequacy profile / explicit `verification_missing` when no CI claim applies.
- Block `session_finished` success paths that require verification when evidence missing (command-kind policy).

### PR-S5 — Slice 5.7: Selective writeback from session trace

- On `session_finished`, propose `memory_record.v1` from session+preflight+verification (2070 summarize optional later; start CT103-deterministic extractor).
- CT103 admission rules: evidence refs, epistemic status, validity, staleness (extend existing memory models).
- Distinct from 6E.2 CI-verified fix memory (keep both; document when each fires).
- Second command retrieves admitted memory (reuse existing retrieval; prove with session_id / issue_id).

### Later (after 5.4–5.7 green)

| Unit | Scope |
|------|--------|
| **8a** | Orbit-style SDLC/evidence edges + provenance on graph queries |
| **8b** | Preflight consumes graph coverage / missing_edges |
| **8c** | Conditional 2070 worker: read-only tools, bounds, `recursive_context_result.v1` |
| **8d** | Deterministic vs small-transformer vs recurrent/SSM bake-off — **not** a gate for enabling optional 2070 |

## Explicit non-goals (this bundle)

- Making 2070 mandatory on every command.
- Replacing Qwen 14B as patch author.
- Claiming principal isolation on CT102 beyond ADR-0008 residual.
- Expanding ACP repair classes beyond `lint_failure` without a new ADR.

## Suggested first implementation prompt (PR-S1)

```text
Implement Slice 5.4a typed agent sessions on CT103 only.

- Add agent_session.v1 + session store under agent-state/projects/{owner}/{repo}/sessions/
- Emit append-only agent.session_started / subject_context_resolved / session_finished|failed|blocked
  via existing append_event ledger with required correlation fields from V4 plan §5a
- Create session at command dispatch; finalize per terminal-ownership table
- Map session_id through job payload (distinct from run_id; CT104 echoes only)
- CLI show/list --json; unit tests for idempotency and required fields
- Do not invoke 2070; do not change repair allowlist; do not add Gitea ack comments yet
- Doc: docs/slice-5.4-typed-sessions.md + tick 5.4a in umbrella after acceptance
```

## Exit criteria (bundle)

Mirror plan DoD items 1–12 for sessions/preflight/verification/writeback; items 13–14 (sandbox already done; bake-off deferred). Homelab: one review + one plan + one fake fix each leave queryable sessions; second plan retrieves selective memory from the first when admitted.

## Related

- [architecture.md](architecture.md)
- [slice-v411-closeout.md](slice-v411-closeout.md)
- [adr/0007-dual-attestation-lifecycle.md](adr/0007-dual-attestation-lifecycle.md) (executor ≠ session)
- [adr/0001-ct102-ci-truth-loop.md](adr/0001-ct102-ci-truth-loop.md) (CI memory vs 5.7)
- V4 plan §5a, §0.2a, Recursive context DoD, Phase 20
