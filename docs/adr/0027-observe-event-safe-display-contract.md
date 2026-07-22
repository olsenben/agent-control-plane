---
id: ADR-0027
title: Observe event safe-display contract precedes storage/streaming/UI
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_shared/models/observe_event.py"
    - "src/agent_control/observe/safe_display.py"
    - "src/agent_control/observe/projection.py"
  symbols:
    - ObserveEventV1
    - FieldClassification
    - safe_display_event
    - classify_field
    - is_prohibited_field_name
decision_type: security
enforcement: hard
risk_level: high
supersedes: []
superseded_by: []
review_after: 2026-10-22
agent_visibility:
  - review
  - developer
---

# Context

V9 (Agent Observatory) adds durable storage (`observe.sqlite`, T02), a protected
SSE stream (T03), and a five-panel UI (T04) that render CT103/CT104/model/
context/sandbox/publish/CI ledger events for humans. Every one of those
surfaces reads from the same underlying event stream, and that stream already
carries payload shapes never designed for display: worker tool-call `args`,
`Authorization`/`X-Gitea-Token` headers, environment snapshots, model prompts,
and injection-scanner snippets of raw untrusted issue/PR content (ADR-0026).

Building storage, streaming, or UI first and retrofitting redaction later is
the wrong order: any event type added between now and the retrofit is
raw-by-default until someone remembers to classify it. Plan hard gate **H1**
requires the opposite: a safe-display contract must exist and be wired into
the read path *before* any sqlite/SSE/UI work lands (T02–T04).

# Decision

1. **`observe_event.v1`** (`agent_shared.models.observe_event.ObserveEventV1`)
   is the only shape any Observatory display surface (API JSON, SSE frame,
   UI template, CLI `observe show`, eval bundle export) may consume. It never
   carries a raw `payload` field.
2. Every payload field is classified into exactly one of four tiers before it
   can reach `ObserveEventV1.display_fields`:
   `allowlisted` (verbatim, length-capped) · `redacted` (fixed placeholder) ·
   `metadata_only` (presence/count descriptor, never the value) ·
   `prohibited` (dropped; only the field *name* is retained, for audit
   visibility into how much was withheld).
3. **Default-deny, two independent layers:**
   - A global field-*name* keyword filter
     (`safe_display.is_prohibited_field_name`) forces `prohibited` for any
     field whose name contains a secret/credential/prompt/header/env/tool-arg
     keyword, regardless of what any per-event-type table says. This is the
     layer that must hold even if a maintainer's table entry is wrong.
   - A per-event-`type` field table (`safe_display._TYPE_FIELD_CLASSIFICATIONS`)
     lists the only fields eligible for `allowlisted`/`redacted`/
     `metadata_only` treatment on a *known* type; anything absent from that
     type's table is `prohibited`.
4. **Unknown event types are display-safe by construction.** If an event's
   `type` is not present in the classification registry at all, *none* of its
   payload field values are ever exposed — only field names, in
   `prohibited_field_names`. New producer event types are unsafe-by-default
   until explicitly classified, never safe-by-default.
5. `observe/projection.py` (the single builder every CLI/API/SSE/UI/eval-bundle
   consumer calls) normalizes every event through `safe_display_event` before
   it is included in `ObservationProjection.events`. There is no code path
   that returns raw ledger `payload` content from this builder.
6. This ADR and its registry are the reference point for T02 (sqlite must
   store/serve `observe_event.v1` rows, not raw payload), T03 (SSE frames
   carry `observe_event.v1`), and T04 (UI templates render
   `display_fields`/`summary`, never raw payload).

# Consequences

- Positive: no future producer event type can leak secrets/prompts/tool-call
  args into the Observatory by omission; the failure mode is "field/event
  invisible until classified," not "field/event leaked until noticed."
- Positive: `agentctl eval export` and bake-off metrics extraction now read
  the same display-safe fields as the UI will, so there is one trust boundary
  to audit, not two.
- Negative: legitimate operator-debugging fields (e.g. a full CI failure log)
  are invisible in the Observatory by default; they must be explicitly
  allowlisted per type or fetched through a separate, explicitly-audited
  artifact route (see the producer-coverage inventory).
- Follow-up: T02 must persist `observe_event.v1` rows (not raw ledger
  payload) so the sqlite projection cannot become a second raw-payload leak
  path; T07/T08 must classify any new decision/CI event types they add before
  wiring them into the stream.
