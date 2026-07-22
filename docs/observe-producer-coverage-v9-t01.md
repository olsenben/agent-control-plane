# Observe producer-coverage inventory — V9 T01

Companion to [ADR-0027](adr/0027-observe-event-safe-display-contract.md) and
[slice-v9-t01-observation-event-contract.md](slice-v9-t01-observation-event-contract.md).
Enumerates every producer domain named in the V9 plan (CT103, CT104, model,
context, sandbox, publish, CI) and classifies each producer's data source
into exactly one of four buckets:

- **existing_typed_event** — already appends a typed `AgentEvent` to the
  CT103 ledger (`agent_control.events.append_event`); a
  `safe_display` classification table entry exists or is a near-term
  candidate.
- **existing_artifact_row** — durable, already persisted (session artifact
  ref, sqlite/JSON row, attestation file) but is *not* itself a ledger
  event; reachable today only via a dedicated artifact route
  (`/api/observe/sessions/{run_id}/artifacts`), not the timeline.
- **new_producer_event_required** — the domain's activity is real and
  happens today, but no typed ledger event exists yet; Observatory
  visibility requires a new producer, which itself must ship with a
  `safe_display` classification table entry (never default to "show
  everything").
- **unsupported_unknown** — out of scope for T01; either the data is
  inherently raw/untrusted (tool stdout/stderr, worker JSONL free text) or
  no design decision has been made yet. Must stay unreachable from any
  display surface until explicitly classified.

## CT103 (control-plane correlation, decisions, verification)

| Source | Event type(s) | Bucket | `safe_display` status |
|---|---|---|---|
| Session lifecycle (`agent_control.session.events`) | `agent.session_started`, `agent.subject_context_resolved`, `agent.session_finished`, `agent.session_failed`, `agent.session_blocked`, `agent.session_worker_event` | existing_typed_event | classified (T01) |
| Memory preflight / recursive context / context packet | `agent.memory_preflight_created`, `agent.memory_preflight_failed`, `agent.recursive_context_completed`, `agent.recursive_context_failed`, `agent.memory_admitted`, `agent.memory_rejected`, `agent.context_packet_created` | existing_typed_event | classified (T01) |
| Verification claims | `agent.verification_requested`, `agent.verification_passed`, `agent.verification_failed`, `agent.verification_missing` | existing_typed_event | classified (T01); `limitations` is `redacted` (may carry free text) |
| Control decisions (ADR context: sandbox/model/approval/policy denials) | `agent.control_decision` | existing_typed_event | classified (T01); `metadata` is `metadata_only` |
| Injection scanner shadow assessments (ADR-0026) | `agent.injection_assessment` | existing_typed_event | classified (T01); `matched_regions`/`detail` are `metadata_only` — raw untrusted snippet never shown |
| Approval lifecycle (`agent_control.approval.events`) | `agent.fix_requested`, `agent.fix_authorized`, `agent.approval_reserved/released/consumed`, `agent.fix_enqueued`, `human.approval_granted`, `human.approval_rejected` | existing_typed_event | **not yet classified** — falls to the unknown-type fallback (safe, but opaque) until a table entry is added; tracked for T07 |
| Model routing attempts (`agent_control.model_route_events`) | `agent.model_route_attempted`, `agent.model_route_failed`, `agent.model_fallback_selected`, `agent.model_call_completed`, `agent.model_all_routes_failed` | existing_typed_event | **not yet classified** — see "model" section below |

## CT104 (workers: fix/repair/review/plan execution)

| Source | Bucket | Notes |
|---|---|---|
| `agent.run_completed` (ingested from CT104 result via `results_ingest.py`) | existing_typed_event | classified (T01); `review_result`/`plan_result`/`fix_result` are `metadata_only` (nested blobs, not yet individually classified); `prompt_hash`/`context_sources` intentionally excluded/limited by the global keyword filter and table |
| CT104 `session_events.jsonl` (`agent_shared.models.events.SessionEvent`: `tool`, `args`, `message`, `content`, `reason`) | unsupported_unknown | worker-local trajectory log, not a CT103 ledger event; `args`/`content`/`message` routinely carry tool-call arguments and raw stdout/stderr. Must never be read directly into the Observatory timeline. A future curated summary event (counts/outcomes only) would be `new_producer_event_required`. |
| Sandbox/execution attestations (`SandboxAttestationV1`, `ExecutionAttestationV1`) | existing_artifact_row | persisted and consumed by publish eligibility checks; not a ledger event today. Exposing a *summary* (attested: true/false, backend, quarantine flag) as a control_decision-style event would be `new_producer_event_required`. |

## model (routing, fallback, call completion)

| Source | Bucket | Notes |
|---|---|---|
| `agent_control.model_route_events` (`MODEL_ROUTE_ATTEMPTED`, `MODEL_ROUTE_FAILED`, `MODEL_FALLBACK_SELECTED`, `MODEL_CALL_COMPLETED`, `MODEL_ALL_ROUTES_FAILED`) | existing_typed_event | Ledger events already exist and are idempotent/typed. **Not yet in the T01 classification table** — until classified they render via the unknown-type fallback (type + envelope only, zero payload values). Payload today includes `provider`, `retry_number`, and likely token/cost counters (`agent_control.model_attempt_budget_store` territory) that must be reviewed field-by-field before allowlisting — do not bulk-allowlist. Tracked as the first classification follow-up (candidate: T02 or T07). |

## context (preflight, recursive context, provenance)

| Source | Bucket | Notes |
|---|---|---|
| Memory preflight / context packet / recursive context ledger events | existing_typed_event | see CT103 table above; classified (T01) |
| Provenance / trust-class labels (`agent_control.observe.provenance`) | existing_artifact_row | computed inline into `ContextPack.provenance_items`, not a standalone ledger event; already trust-labeled (ADR-0017), safe to surface via the artifacts route |

## sandbox (SRT / bwrap execution backend)

| Source | Bucket | Notes |
|---|---|---|
| `agent_control.aci.backends.srt` / `agent_control.sandbox.command_runner` / `agent_workers.executor.lifecycle` | unsupported_unknown | No dedicated ledger event type for sandbox lifecycle (launch/deny/teardown) exists yet; only `agent.control_decision` with `kind=sandbox_denied` surfaces a *denial*, not the full lifecycle. A `agent.sandbox_lifecycle` event (backend, decision, quarantine reason — never raw command output) would be `new_producer_event_required`. |
| Sandbox attestations | existing_artifact_row | see CT104 table above |

## publish (CT103 publish brokerage, ADR-0004)

| Source | Bucket | Notes |
|---|---|---|
| `agent_control.publish.broker` / `agent_control.publish.eligibility` | unsupported_unknown | No ledger event is emitted on publish decision/execution today; publish state is tracked on `AgentSession.session_comment_id`-adjacent fields and `WorkItemApproval.publish_state` (an artifact field, not an event). A `agent.publish_decision` / `agent.publish_executed` event (target ref, decision, PR/commit refs — never tokens) would be `new_producer_event_required`. Until it ships, publish activity is invisible to the Observatory timeline by design (fails closed, not open). |

## CI (CT102 aggregate truth, ADR-0001)

| Source | Event type(s) | Bucket | Notes |
|---|---|---|---|
| `agent_control.ci.events` | `agent.fix_ci_observed`, `agent.fix_ci_verdict_changed`, `agent.fix_ci_failure_evidence_collected`, `agent.fix_ci_failure_evidence_unavailable`, `agent.fix_ci_repair_requested`, `agent.fix_ci_repair_blocked`, `agent.fix_ci_repair_started`, `agent.fix_ci_repair_pushed`, `agent.fix_ci_repair_exhausted`, `agent.fix_ci_repair_stale` | existing_typed_event | Ledger events exist and are already redaction-aware upstream (`REDACTION_POLICY_VERSION` / `TRUNCATION_STRATEGY` in `agent_shared.models.ci.FailureEvidenceManifest`). **Not yet in the T01 classification table** — renders via the unknown-type fallback today. Tracked for T08 (CT102 CI into observe stream), which must add the table entries as part of that slice, not assume the unknown-type fallback is sufficient for a UI panel. |

## Summary

| Bucket | Count (producer groups) |
|---|---|
| existing_typed_event, classified in T01 | 6 (session lifecycle, memory/context, verification, control_decision, injection_assessment, run_completed) |
| existing_typed_event, not yet classified | 3 (approval lifecycle, model routing, CI fix-loop) — safe by the unknown-type fallback, but opaque; each owning slice (T07 approvals/decisions, T04/T07 model, T08 CI) must add table entries before claiming UI coverage |
| existing_artifact_row | 2 (attestations, provenance/context-pack) |
| new_producer_event_required | 3 (sandbox lifecycle, publish decision/execution, curated CT104 trajectory summary) |
| unsupported_unknown | 2 (raw CT104 `session_events.jsonl`, raw sandbox/publish execution internals) |

No bucket above resolves to "expose raw payload directly." That is the T01
deliverable: every domain either has a classified path, a documented
artifact-route path, a documented gap to close in a later ticket, or is
explicitly marked out of reach.
