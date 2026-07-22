# Handoff -- coordinator-handoff-031

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 031 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T06 |
| Tip SHA (ACP) | `08382e2` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-031.md
ticket: T06
status: Deploy gate
tip_sha: 08382e2
tests: 808 passed
ruff: All checks passed!
blocker: none
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- `Settings.observe_public_base_url` (`agent_control/config.py`) -- optional,
  default `None` (no LAN/HTTP default). A new
  `validate_observe_public_base_url` startup `model_validator` fails closed
  on a malformed value (must be an absolute `http`/`https` scheme+host URL,
  no path/query/fragment) and requires `https` whenever
  `OBSERVE_COOKIE_SECURE=true` (its default) -- "public/secure mode" per
  the ticket. Unset never raises.
- New `agent_control/observe_links.py` module is the single place that
  turns the base URL + a `run_id` into a link: a conservative URL-safe
  `run_id` allowlist checked *before* interpolation
  (`^[A-Za-z0-9._:-]{1,128}$`, rejecting whitespace/`/`/backticks/brackets/
  parens/newlines), `build_observe_session_url` (fail-closed `None` on
  either unset base or unsafe `run_id`), `observe_link_line` (the
  `"Observe: <url>"` Markdown line or `None`), and `observe_config_warning`
  for the startup log + `/readyz`.
- Three existing comment/ack builders now call `observe_link_line` and
  append the line only when non-`None`, replacing their previous
  unconditional relative-path text:
  `format_invocation_started` (`invocation_ack.py`),
  `render_session_comment_body` (`observe/comment_projection.py`, T02's
  versioned session-status comment), and the NL-invocation "session
  created" stub (`nl_invocation_wire.py`, T07-F08). `format_invocation_terminal`
  is unchanged (out of this ticket's explicit scope).
- `readiness.py`'s `/readyz` gains an informational
  `checks.observe_public_base_url` (`"configured"`/`"unset"`) that never
  changes the `ready`/`degraded`/`not_ready` status;
  `webhook_server.create_app` logs the config warning once at startup
  (not per-request) when unset.
- `docs/gitea-custom/extra_tabs.tmpl` + `docs/gitea-custom/README.md`:
  version-pinned to the live homelab Gitea (`1.26.2`, confirmed via
  `GET /api/v1/version` against `git.ham-sup-lo.com`), with upstream
  `templates/repo/header.tmpl` / `models/repo/repo.go` checksums recorded.
  The spike (source-read against the pinned tag, no CT100 filesystem
  access available from this environment) confirms the exact
  `{{template "custom/extra_tabs" .}}` insertion point and that
  `.Repository.OwnerName`/`.Repository.Name` -- not the unverified
  `{{.RepoLink}}` shown in third-party examples -- are the right fields for
  the `/observe/repos/{owner}/{repo}` link. The shipped template requires a
  human to substitute a literal `OBSERVE_PUBLIC_BASE_URL_PLACEHOLDER`
  before install and explicitly instructs not installing the file at all
  while `OBSERVE_PUBLIC_BASE_URL` is unset. Full install + upgrade
  checklists are in the README.
- New tests: `tests/test_v9_t06_observe_public_links.py` (35 tests) --
  `Settings` validator (unset ok; relative/non-http/path/query rejected;
  http rejected under secure mode, accepted only with
  `OBSERVE_COOKIE_SECURE=false`); `observe_links` helpers (safe/unsafe
  `run_id` shapes incl. injection-shaped strings, URL building, trailing-
  slash normalization); all three comment/ack call sites omit the line
  when unset and produce the exact expected link when configured;
  `/readyz` reflects both states without changing overall status.
- `ruff check .` clean; full suite `808 passed` (up from 773 at the T04
  land-time baseline; 35 new T06 tests). Two commits on top of `b914d30`:
  `e28cedb` (pending T04 deploy-verify closeout that had not yet been
  committed when this ticket started -- ledger T04 Deploy gate -> Done,
  tip `8fb905d`) and `08382e2` (this ticket's code + tests + docs). Push
  pending this handoff's ledger commit (established wave pattern).

## Explicit non-goals honored

- No live install onto CT100 -- outside the documented SSH surface
  (`.cursor/rules/ssh-ct103-ct104.mdc` covers CT103/CT104 only); the
  template-context spike is source-level against the pinned upstream tag,
  not a live browser check.
- No change to `format_invocation_terminal`, T03's SSE wire format, T04's
  five-panel UI, or `observe.sqlite`'s schema (T02).
- No repo-level Observatory HTML page -- `extra_tabs` links to the existing
  `/observe/repos/{owner}/{repo}` JSON route (V6 T03).
- `OBSERVE_PUBLIC_BASE_URL` is never defaulted to a LAN/HTTP address, even
  for local dev.

## Evidence pointers

- Code: `src/agent_control/config.py` (diff: new field + validator),
  `src/agent_control/observe_links.py` (new),
  `src/agent_control/invocation_ack.py` (diff),
  `src/agent_control/observe/comment_projection.py` (diff),
  `src/agent_control/nl_invocation_wire.py` (diff),
  `src/agent_control/readiness.py` (diff),
  `src/agent_control/webhook_server.py` (diff)
- Docs: `docs/slice-v9-t06-observe-public-links.md`,
  `docs/gitea-custom/README.md`, `docs/gitea-custom/extra_tabs.tmpl`
- Tests: `tests/test_v9_t06_observe_public_links.py` (new, 35 tests)

## Decisions the next coordinator must honor

1. `agent_control/observe_links.py` is the only path from
   `OBSERVE_PUBLIC_BASE_URL` + a `run_id` to a link. Any future comment/ack
   builder that wants an Observe link must call `observe_link_line`
   (or `build_observe_session_url`) and skip the line entirely when it
   returns `None` -- never fall back to a bare relative path or construct
   a URL by hand.
2. `is_url_safe_run_id`'s allowlist must be checked before any future code
   interpolates a `run_id` (or similar request-derived identifier) into a
   URL that will be embedded in a Gitea comment or a Go template; treat a
   failing check as "omit", not "sanitize and continue".
3. `docs/gitea-custom/extra_tabs.tmpl` must not be installed on CT100 while
   `OBSERVE_PUBLIC_BASE_URL` is unset on CT103, and must be re-edited +
   Gitea-restarted if that value ever changes -- there is no live lookup.
4. Any future Gitea-version bump must repeat the upgrade checklist in
   `docs/gitea-custom/README.md` before trusting `extra_tabs.tmpl` again.

## Next coordinator: first actions

1. `git push origin main` (this handoff + ledger commit, on top of
   `08382e2`) so CT102 Actions runs per the homelab deploy pattern.
2. Deploy-verify on CT103 (+CT104 if applicable): confirm CI green on the
   pushed tip, `/readyz` still `ok`/`degraded` as before (new
   `observe_public_base_url` check present, `"unset"` expected since no
   deploy `.env` sets it yet), and that Gitea comment/ack posting is
   unchanged in shape (no Observe line, since `OBSERVE_PUBLIC_BASE_URL`
   stays unset in this deploy) before flipping T06 to Done.
3. Optional, human, non-blocking: work through
   `docs/gitea-custom/README.md`'s "Install on CT100" checklist once a
   value for `OBSERVE_PUBLIC_BASE_URL` is chosen and set on CT103.
4. Start T07 (decisions + artifact dispositions) per the epic spine
   (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 -> T07 ∥ T08`).

## Open risks (one line each)

- `OBSERVE_PUBLIC_BASE_URL` is not yet set anywhere in a real deploy `.env`
  -- Observe links stay omitted end-to-end until a human chooses and sets
  a value; this is the intended fail-closed default, not a defect.
- `extra_tabs.tmpl`'s context spike is source-level, not live-verified on
  CT100; the "Live confirmation method" step in
  `docs/gitea-custom/README.md` (temporary `RUN_MODE=dev` +
  `{{ $ | DumpVar }}`) should be run once during the human install, before
  relying on the tab in production.
