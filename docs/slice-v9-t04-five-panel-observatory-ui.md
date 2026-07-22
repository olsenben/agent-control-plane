# Slice V9 T04 -- Jinja2 + HTMX five-panel Observatory UI

**Status:** Done -- 2026-07-22
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**ADR:** [0031-observatory-five-panel-ui-text-safe-rendering.md](adr/0031-observatory-five-panel-ui-text-safe-rendering.md)
**Depends on:** T03 (done, tip `dae78e3`)

## Goal

Replace the V6-era inline-HTML session page with the epic's protected
Jinja2+HTMX five-panel Observatory UI, reusing the read paths already
established by T01/T02/T03/T05 rather than inventing a second one:

1. **Current state** -- sourced from `session_observation` (T02, H6: the
   canonical, redacted mirror of the live `AgentSession`), with a fallback
   to the same curated builder the projector itself uses when no event has
   been projected yet for a brand-new session.
2. **Decision timeline** -- paginated over `observe.sqlite`'s
   `observe_events` index (T02), rendering only already display-safe
   `observe_event.v1` payloads (T01 `safe_display_event`) -- never a second,
   raw-payload read path.
3. **Decisions** -- placeholder text pointing at the timeline above;
   structured decision + evidence rendering ships in T07.
4. **Live logs** -- server-rendered on initial load from the same
   `observe.sqlite` read as panel 2's most recent rows, kept current by an
   `EventSource` against T03's protected SSE stream (progressive
   enhancement) with an HTMX `hx-trigger="every 5s"` poll fragment as the
   no-JS/JS-disabled fallback -- one view builder, two delivery mechanisms,
   so neither can render anything the other wouldn't.
5. **Artifacts** -- metadata-only (`digest`/`byte_size`/`relative_path`/
   `schema_name`/`created_at`) index of `AgentSession`'s `SessionArtifactRef`
   fields; `disposition` is fixed to `metadata_only` for every row until T07
   adds real dispositions.

Hard requirement: text-safety. HTML, ANSI escape sequences, and Markdown in
any stored string must render as inert text everywhere this UI touches it
(page source, HTMX fragment, SSE frame) -- never as markup, terminal color
codes, or script. No raw/prohibited payload field value may reach any of
those three surfaces; only field *names* may (existing audit-visibility
behavior from T01/T02, unchanged here). Panel 2's pagination must not
require JavaScript.

## What shipped

1. **`agent_control/observe/ui.py`** (new) -- view-model layer between the
   already-safe stores (`ObserveStore`, `AgentSession`) and the templates.
   Every function returns a plain dict of primitives/lists/dicts that were
   already display-safe *before* this module touched them; nothing here
   introduces a new raw-payload path:
   - `current_state_view(session, store)` -- panel 1, reading
     `store.get_session_observation(session_id)` first and falling back to
     `build_session_observation_row(session)` (the same builder T02's
     projector uses) so the "live" and "fallback" code paths can never
     disagree about which fields are display-safe.
   - `timeline_page_view(store, run_id, after_sequence, limit)` -- panel 2,
     keyset pagination over `store.list_events_for_run` /
     `count_events_for_run` using the durable `projection_sequence` (H3) as
     the cursor; `TIMELINE_PAGE_SIZE = 25`.
   - `live_log_view(store, run_id, limit)` -- panel 4's baseline snapshot:
     the latest `LIVE_LOG_SIZE = 20` rows, newest first. Used identically by
     the initial full-page render and the HTMX poll fragment route, so a
     JavaScript-disabled browser sees the exact same safe-display data the
     SSE-enhanced version would have shown.
   - `artifacts_view(session)` -- panel 5, reading the four
     `SessionArtifactRef`-typed attributes already exposed by the JSON
     artifacts endpoint (`memory_preflight`, `context_packet`,
     `recursive_context`, `verification`) and never the artifact content
     itself.
   - `display_value(value)` -- a Jinja filter that only normalizes *shape*
     (dict/list -> compact `json.dumps`); it never marks anything `Markup`/
     "safe", so Jinja's own autoescaping still applies to whatever it
     returns. A hostile string that reaches this filter as a plain `str`
     round-trips through unchanged and is escaped by the template exactly
     like any other text node.
   - `_build_templates()` constructs one process-wide `Jinja2Templates`
     (autoescape on for `.html`) with `display_value` registered as a
     filter; `templates` is the module-level instance both `ui.py`'s own
     callers and `routes.py` import.
2. **`agent_control/observe/templates/`** (new) -- `session_detail.html`
   (the full five-panel document) and `_live_log_rows.html` (the panel-4
   partial, `{% include %}`-ed by the full page and returned standalone by
   the HTMX fragment route). No template ever disables autoescaping
   (`|safe`, `{% autoescape false %}`) anywhere in this ticket's code.
3. **`agent_control/observe/static/htmx.min.js`** (new, vendored) --
   htmx 1.9.12, served unauthenticated from a new `/observe/static` mount
   (`register_observe_routes`). Not a display surface (carries no
   session/observation data), so it is exempt from the observe auth gate
   the same way `/observe/oauth/*` already is, and falls under the
   `ENFORCE_PUBLIC_SURFACE_RESTRICTION` allowlist's existing `/observe`
   prefix exemption.
4. **`agent_control/observe/routes.py`**:
   - `observe_session_page` rewritten to run the existing T05 auth check
     (identity before resource existence, `authorize_repo_read` before any
     data fetch) and then render `session_detail.html` from the four view
     builders above, plus `run_id_urlsafe` (URL-quoted `run_id`, used for
     the SSE stream URL and the HTMX fragment URL so a hostile `run_id`
     can never break out of an HTML attribute or a URL path segment).
   - `observe_session_live_fragment` (new) -- `GET
     /observe/sessions/{run_id}/live-fragment`, panel 4's HTMX poll target.
     Runs the exact same 401/redirect/403/503 auth matrix as every other
     run_id-keyed route, re-checked on every poll (never a weaker check
     than the full page or the SSE stream) and renders
     `_live_log_rows.html` from the same `live_log_view` builder.
   - `register_observe_routes` mounts `/observe/static` via
     `starlette.staticfiles.StaticFiles`.
5. **`pyproject.toml`** -- added `jinja2>=3.1` (already a transitive
   dependency of `fastapi`'s `Jinja2Templates`, now declared directly since
   this ticket is the first to import it explicitly).
6. **Tests**: `tests/test_v9_t04_five_panel_ui.py` (new, 20 tests) --
   see Verification below.

## Text-safety implementation

- **HTML**: Jinja2's autoescape (on by default for `.html` templates via
  `Jinja2Templates`) escapes every interpolated value; `display_value`
  never marks a value `safe`. A stored `<script>...</script>` renders as
  `&lt;script&gt;...&lt;/script&gt;` text, never as a live tag, on the full
  page, the HTMX fragment, and (pre-existing, T01/T03 behavior, unchanged)
  the SSE frame's JSON `data:` payload.
- **ANSI**: escape sequences are just bytes inside an already-`str` field;
  they are never interpreted by a terminal (this is a browser page, not a
  TTY) and are escaped as ordinary text alongside any other character in
  the same string -- no separate ANSI-stripping step exists or is needed
  because nothing in this rendering path ever writes to a terminal.
- **Markdown**: no Markdown renderer is used anywhere in this ticket;
  `display_value`/Jinja render every string as plain escaped text, so
  `*bold*`, `# heading`, etc. in a stored summary appear as those literal
  characters, never as formatted output.
- **No raw/prohibited payloads**: `_parse_event_row` (in `ui.py`) only ever
  reads `display_fields`, `metadata_only_field_names`,
  `redacted_field_names`, and `prohibited_field_names` off the already-safe
  `observe_event_json` blob -- the same four keys T01's `safe_display_event`
  produces. `prohibited_field_names` supplies *names* for an audit-visible
  "withheld: ..." note; their values are never read.

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 773 passed
```

New test file: `tests/test_v9_t04_five_panel_ui.py` (20 tests), covering:

- All five panels render server-side on the initial `TestClient.get` (no
  JavaScript execution involved).
- Panel 3 (decisions) and panel 5 (artifacts) show the documented
  placeholder text when no T07 data exists yet.
- Panel 1 mirrors `AgentSession`/`session_observation` fields, including
  the fallback path for a session with zero projected events.
- A hostile summary (`<script>...</script>`, ANSI escape bytes, `&`,
  Markdown) renders as escaped text on the full page and the live-log HTMX
  fragment, never as a live `<script>` tag.
- A raw ledger event carrying a prohibited-named field (`auth_header`) never
  leaks its value into the rendered page; only the field name appears.
- Panel 2 pagination works via plain `<a href="?after_sequence=...">`
  links with no script involved, verified against a specific `<td>` cell
  to distinguish it from panel 4's independent "most recent events"
  snapshot.
- An empty timeline shows a placeholder, not an error.
- The live-fragment route enforces the same auth matrix as every other
  run_id-keyed route (401 when unauthenticated) and 404s for an unknown
  `run_id`.
- The initial page embeds panel 4's snapshot inline (no-JS visibility).
- The SSE URL is carried via a `data-stream-url` attribute (auto-escaped),
  never interpolated into an inline `new EventSource(...)` string literal.
- The vendored `htmx.min.js` static asset is served unauthenticated.
- The detail page's existing auth matrix (302 redirect for HTML,
  unchanged from T05) and 404-for-unknown-run_id behavior are preserved.

## Explicit non-goals honored

- No structured decisions/evidence rendering (T07) -- panel 3 is a
  placeholder pointing at the existing timeline.
- No real artifact dispositions (`redacted_text_view`,
  `downloadable_redacted_copy`) -- panel 5 is metadata-only, fixed
  `disposition = "metadata_only"` (T07).
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` Gitea integration (T06).
- No second live-update transport -- panel 4 reuses T03's existing SSE
  route as-is; only a new HTMX poll fallback and an initial server-rendered
  snapshot were added around it.
- No change to `observe.sqlite`'s schema, the safe-display contract (T01),
  or the SSE wire format (T03) -- this ticket only adds a new read-side
  rendering layer on top of all three.

## Non-goals

- A client-side JavaScript framework/bundler -- htmx is a single vendored
  script; the `EventSource` enhancement is a small inline script with no
  build step.
- Full CSS theming/branding -- inline `<style>` only, functional not
  polished.
- Server-side session/timeline caching -- every panel re-reads
  `observe.sqlite`/the session index on each request; acceptable at
  homelab scale (matches T03's existing per-connection read pattern).
