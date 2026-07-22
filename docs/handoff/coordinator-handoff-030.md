# Handoff -- coordinator-handoff-030

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 030 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T04 |
| Tip SHA (ACP) | `b914d30` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-030.md
ticket: T04
status: Deploy gate
tip_sha: b914d30
tests: 773 passed
ruff: All checks passed!
blocker: none
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- Session detail page (`observe_session_page`) rewritten from V6's inline
  HTML string into a Jinja2-rendered five-panel document
  (`templates/session_detail.html`), behind the same T05 auth matrix
  (identity/401-redirect before resource existence; `authorize_repo_read`
  before any data fetch):
  1. Current state -- `agent_control/observe/ui.py`'s `current_state_view`
     reads T02's `session_observation` row (H6) first, falling back to the
     same `build_session_observation_row` builder the projector itself uses
     for a brand-new session with no projected events yet.
  2. Decision timeline -- `timeline_page_view` keyset-paginates
     `observe.sqlite`'s `observe_events` (T02) over the durable
     `projection_sequence` (H3); rendered as plain `<a href="?after_sequence=...">`
     links, no JavaScript required to page through it.
  3. Decisions -- placeholder text pointing at the timeline above;
     structured decision/evidence rendering is explicitly T07's scope.
  4. Live logs -- `live_log_view`'s latest-events snapshot renders inline on
     first load (visible with JavaScript disabled) and is kept current
     two ways: a progressive-enhancement `EventSource` against T03's
     existing protected SSE stream, and a new HTMX poll fragment route
     (`GET /observe/sessions/{run_id}/live-fragment`, `hx-trigger="every 5s"`)
     that runs the exact same auth matrix as every other run_id-keyed
     route, re-checked on every poll.
  5. Artifacts -- `artifacts_view` reads `AgentSession`'s
     `SessionArtifactRef` fields (digest/byte_size/relative_path/
     schema_name/created_at only, never content); `disposition` fixed to
     `"metadata_only"` until T07.
- Text-safety: one process-wide `Jinja2Templates` instance (autoescape on
  for `.html`, never disabled anywhere in this ticket) plus a
  `display_value` filter that only normalizes shape (dict/list -> compact
  JSON text) and never marks a value `Markup`/safe. A stored
  `<script>...</script>`, ANSI escape bytes, or Markdown syntax renders as
  inert escaped text on the full page and the HTMX fragment; the SSE
  frame's JSON payload was already safe from T01/T03 and is unchanged.
  `prohibited_field_names` surface only field *names* (audit visibility),
  never the withheld values, matching T01/T02's existing invariant at this
  new rendering surface.
- Request-derived `run_id` reaches HTML only via an auto-escaped
  `data-stream-url` attribute (read back via `getAttribute`, never
  interpolated into an inline `new EventSource(...)` string literal) and
  via `urllib.parse.quote`d URL path segments for the SSE/fragment routes.
- New vendored static asset `htmx.min.js` (1.9.12) served unauthenticated
  from a new `/observe/static` mount -- not a display surface, exempt from
  the observe auth gate the same way `/observe/oauth/*` already is.
- `pyproject.toml`: `jinja2>=3.1` now declared directly (previously only a
  transitive dependency via `fastapi`'s `Jinja2Templates`).
- ADR-0031 accepted; slice doc
  [docs/slice-v9-t04-five-panel-observatory-ui.md](../slice-v9-t04-five-panel-observatory-ui.md).
- New tests: `tests/test_v9_t04_five_panel_ui.py` (20 tests) -- all five
  panels render; placeholder text for panels 3/5; panel 1 mirrors
  `AgentSession`/`session_observation` incl. the no-projection-yet
  fallback; hostile-string escaping on the full page and the live-log
  fragment; no raw/prohibited payload value in page source (field name
  retained); pagination via `<td>`-scoped assertions distinguishing panel
  2 from panel 4; empty-timeline placeholder; live-fragment auth (401) and
  404; initial-load no-JS visibility of the live-log snapshot; SSE URL via
  attribute not inline script; static asset served unauthenticated;
  existing detail-page auth matrix (302 redirect, 404 unknown run) unchanged.
- `ruff check .` clean; full suite `773 passed` (up from 756 passed at the
  T03 handoff baseline -- 17 new T04 tests; also fixed two pre-existing,
  unrelated `F401` lint errors in the already-untracked
  `scripts/_v9_t03_smoke_remote.py` scratch script so `ruff check .`
  returns clean, per this workspace's lint-before-commit rule).
- Committed on `main` in two commits on top of `dae78e3`: `f57f849`
  (docs-only V9 T03 deploy-verify closeout that was already decided but
  not yet committed when this ticket started -- ledger T03 Deploy gate ->
  Done, `agent-facts.json` re-sign) and `b914d30` (this ticket's code +
  tests + docs). Push pending this handoff's ledger commit (matching the
  established wave pattern).

## Explicit non-goals honored

- No structured decisions/evidence rendering (T07) -- panel 3 is a
  placeholder.
- No real artifact dispositions (T07) -- panel 5 is metadata-only, fixed
  `disposition = "metadata_only"`.
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` Gitea integration (T06).
- No second live-update transport -- panel 4 reuses T03's SSE route
  unmodified; only a new HTMX poll fallback and initial server-rendered
  snapshot were added around it.
- No change to `observe.sqlite`'s schema, the safe-display contract (T01),
  or the SSE wire format (T03).

## Evidence pointers

- Code: `src/agent_control/observe/ui.py` (new),
  `src/agent_control/observe/templates/session_detail.html` (new),
  `src/agent_control/observe/templates/_live_log_rows.html` (new),
  `src/agent_control/observe/static/htmx.min.js` (new, vendored),
  `src/agent_control/observe/routes.py` (diff: `observe_session_page`
  rewritten, `observe_session_live_fragment` added, static mount added),
  `pyproject.toml` (diff: `jinja2>=3.1`)
- Tests: `tests/test_v9_t04_five_panel_ui.py` (new, 20 tests)
- Docs: ADR-0031, `docs/slice-v9-t04-five-panel-observatory-ui.md`

## Decisions the next coordinator must honor

1. The view-model layer (`agent_control/observe/ui.py`) is the only path
   from a store (`ObserveStore`, `AgentSession`) to a template -- any new
   panel (T06/T07/T08) must add a new builder function there rather than
   reading `observe.sqlite`/session data directly inside a route handler
   or a template.
2. Never disable Jinja autoescape (`|safe`, `Markup(...)`,
   `{% autoescape false %}`) anywhere in this template set; never have a
   view-model function return a value already marked safe. Per ADR-0031,
   treat introducing either as requiring its own review.
3. `prohibited_field_names` may only ever surface field *names* to any
   template; never read or render the withheld value itself. This applies
   to T07's future decisions/artifact-disposition rendering too.
4. Any request-derived string (especially `run_id`) that must appear
   inside an inline `<script>` block belongs in an auto-escaped HTML
   attribute read back via `getAttribute`/`dataset`, never concatenated
   directly into a JS string literal.
5. Panel 4's dual-delivery pattern (one view builder, HTMX poll fragment +
   progressive `EventSource` enhancement, both reachable via the same auth
   check) is the template for any future live-updating panel -- do not
   introduce a fragment/poll route with a weaker auth check than its
   corresponding full-page route.

## Next coordinator: first actions

1. `git push origin main` (this handoff + ledger commit, on top of
   `b914d30`) so CT102 Actions runs per the homelab deploy pattern.
2. Deploy-verify on CT103 (+CT104 if applicable): confirm CI green on the
   pushed tip, `/readyz` still ok, and a browser/`curl` smoke of
   `GET /observe/sessions/{run_id}` (five panels present, hostile-string
   escaping, `/observe/static/htmx.min.js` reachable) before flipping T04
   to Done. This is also the first opportunity to live-check the NPM
   `proxy_buffering off;` follow-up flagged in T03's slice doc, now that a
   real browser `EventSource` is in play.
3. Start T06 (Gitea `extra_tabs` + `OBSERVE_PUBLIC_BASE_URL` fail-closed
   links) per the epic spine (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 ->
   T07 ∥ T08`).

## Open risks (one line each)

- NPM `proxy_buffering off;` for the SSE path (flagged in T03's slice doc)
  is still not live-verified from this sandbox; T04's real `EventSource`
  makes this the first deploy-verify pass where it can actually be
  checked with a browser pointed at CT103 through NPM.
- Panel 4's `EventSource` enhancement degrades silently (per its own
  `try/catch`) if the browser lacks `EventSource` support or the SSE
  connection fails for a reason other than a clean `degraded` frame; the
  HTMX 5-second poll is the only guaranteed live-refresh path in that
  case -- acceptable at this ticket's scope but worth surfacing a visible
  "live updates paused" indicator in a future ticket if this proves
  confusing in practice.
