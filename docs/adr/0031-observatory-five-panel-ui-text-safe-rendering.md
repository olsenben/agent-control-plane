---
id: ADR-0031
title: Observatory five-panel UI renders only pre-validated safe-display data as inert text
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_control/observe/ui.py"
    - "src/agent_control/observe/routes.py"
    - "src/agent_control/observe/templates/**"
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-22
agent_visibility:
  - review
  - developer
---

# Context

V9 T01 (ADR-0027) established `observe_event.v1`'s four-tier field
classification (`display_fields` / `metadata_only_field_names` /
`redacted_field_names` / `prohibited_field_names`) as the single safe-display
contract; T02 (ADR-0028) persisted that contract's output durably in
`observe.sqlite`; T03 (ADR-0030) streamed it live over protected SSE. This
ticket (T04) adds the first *browser-rendered* consumer of all three --
session state, decision timeline, and live logs are now HTML, not just JSON.
Rendering as HTML introduces a failure mode none of T01-T03 had to consider:
a stored string that is merely inert JSON text in an API response becomes a
live `<script>` tag, a broken layout, or (via ANSI/Markdown) a misleading
rendering if the template layer ever emits it as markup instead of text. The
epic's requirement is explicit: HTML, ANSI, and Markdown in any stored
string must render as inert text everywhere this UI touches it, and no raw
or prohibited payload value may reach page source, an HTMX fragment, or an
SSE frame -- only field names may.

A second, related risk is specific to this ticket's introduction of
`EventSource`/HTMX-driven URLs into HTML: a `run_id` or other request-derived
string interpolated into a URL or, worse, directly into an inline
`<script>`'s string literal, could itself become an injection vector
independent of anything stored in `observe.sqlite`.

# Decision

1. **One rendering boundary, autoescape always on, never disabled.** All
   five panels render through a single `Jinja2Templates` instance
   (`agent_control.observe.ui.templates`) built once and reused by every
   route. `Jinja2Templates` autoescapes `.html` templates by default; no
   template in this ticket uses `|safe`, `Markup(...)`, or
   `{% autoescape false %}` anywhere, and this ADR treats introducing any of
   those three as a decision requiring its own review, not a template
   author's local choice.
2. **The view-model layer normalizes shape only, never marks anything
   safe.** `agent_control.observe.ui`'s `display_value` filter and its four
   panel-builder functions (`current_state_view`, `timeline_page_view`,
   `live_log_view`, `artifacts_view`) return only `str`/`int`/`bool`/`None`/
   plain `dict`/`list` values, sourced exclusively from data already
   classified as display-safe upstream (`session_observation`,
   `observe_events.observe_event_json`'s `display_fields`/
   `*_field_names` keys, `SessionArtifactRef` metadata fields). No function
   in this module reads a `payload`/raw-ledger-event field directly, and
   none constructs a `Markup` value. This means the autoescape guarantee in
   (1) is never accidentally bypassed by a helper that "already knows the
   value is safe" -- nothing upstream of the template is ever trusted to
   make that call.
3. **Prohibited fields surface names only, never values, at this layer
   too.** `_parse_event_row` copies `prohibited_field_names` (a list of
   strings) from the safe-display payload for an audit-visible "withheld:
   ..." note; it never reads whatever raw value T01's classifier withheld.
   This mirrors T01/T02's existing invariant at the one new place (browser
   HTML) an operator could otherwise be tempted to "just render everything
   for convenience."
4. **Request-derived identifiers reach HTML only via auto-escaped
   attributes, never via inline script string interpolation.** The SSE
   stream URL (which embeds `run_id`) is written into a `data-stream-url`
   HTML attribute (subject to the same autoescaping as any other
   interpolated value) and read back by JavaScript via `getAttribute`;
   `run_id` is never concatenated into a `new EventSource(...)` string
   literal inside a `<script>` block, where autoescaping would not apply to
   whatever ends up inside the quotes. `routes.py` additionally passes
   `run_id_urlsafe = urllib.parse.quote(run_id, safe="")` for the URL path
   segments (SSE endpoint, HTMX fragment endpoint) so a hostile `run_id`
   cannot break out of the URL syntax it is embedded in either.
5. **Panel 4 (live logs) is dual-delivered from one view builder, so
   neither delivery path can show something the other wouldn't.** The
   initial page render, the HTMX poll fragment
   (`GET /observe/sessions/{run_id}/live-fragment`), and the progressive
   `EventSource` enhancement all ultimately source the same
   `observe.sqlite` rows through the same safe-display contract; a browser
   with JavaScript disabled sees the server-rendered snapshot from initial
   load and nothing else, never a degraded or differently-escaped view.
   The HTMX fragment route runs the identical 401/redirect/403/503 auth
   matrix as every other run_id-keyed route, re-checked on every poll --
   T04 introduces no separate, weaker auth path for "just a UI fragment."
6. **Panel 2's pagination requires no JavaScript.** `timeline_page_view`
   exposes `next_after_sequence`/`has_more` computed from
   `observe.sqlite`'s durable `projection_sequence` (H3); the template
   renders these as plain `<a href="?after_sequence=...">` links, so moving
   through the decision timeline works identically with JavaScript on or
   off.

# Consequences

- Positive: text-safety is enforced structurally (autoescape + "never
  return a `Markup` value") rather than by convention at each of the five
  panels separately -- a future panel added to this same template set
  inherits the guarantee automatically as long as it reuses
  `Jinja2Templates`/`display_value` rather than hand-building HTML strings.
- Positive: T04 adds no new raw-payload read path -- every panel's data
  originates from a store/field-set T01-T03 already classified as
  display-safe, so a defect in this ticket's rendering code can at worst
  mis-render already-safe data, never newly expose a previously-withheld
  value.
- Positive: the dual-delivery design for panel 4 means the SSE
  enhancement's presence or absence (progressive enhancement, may fail
  silently per T03's `try/catch`) never changes what a JS-disabled browser
  is able to see, only how promptly a JS-enabled one sees new rows.
- Negative: no client-side Markdown/ANSI rendering exists for this UI even
  where it might improve readability (e.g. a summary that happens to be
  valid Markdown) -- an explicit trade-off; adding a sanitizing
  renderer for either would need its own review given the injection
  surface both formats represent.
- Follow-up: T06 (Gitea `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL`) and T07
  (decisions + artifact dispositions) should extend this same
  template/view-model boundary rather than introducing a second one; T07
  in particular must keep prohibited-field values out of whatever new
  "decision" or "downloadable" rendering it adds, per (3) above.
