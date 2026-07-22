# Slice V9 T06 -- OBSERVE_PUBLIC_BASE_URL fail-closed Observe links + Gitea extra_tabs

**Status:** Done -- 2026-07-22 (deploy verify [deploy-verify-v9-t06-20260722.md](handoff/deploy-verify-v9-t06-20260722.md), tip `4a4998a`)
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Handoff:** [coordinator-handoff-031.md](handoff/coordinator-handoff-031.md)
**Depends on:** T04 (done, tip `8fb905d`)
**Hard gate:** H8 -- OBSERVE_PUBLIC_BASE_URL fail-closed

## Goal

Give the Observatory an externally reachable link surface without ever
guessing a LAN/HTTP address: a new `OBSERVE_PUBLIC_BASE_URL` setting that
fails closed (omit the link, log/report a config warning) when unset, feeds
the one Gitea-comment link-building path used by every comment projector in
this codebase, and a documented, version-pinned Gitea `extra_tabs.tmpl`
snippet for a human to install on CT100.

## What shipped

1. **`Settings.observe_public_base_url`**
   (`agent_control/config.py`) -- optional, default `None` (no LAN/HTTP
   default of any kind). A new `validate_observe_public_base_url` startup
   `model_validator` fails closed on malformed input: the value must be an
   absolute `http`/`https` URL with no path/query/fragment, and must be
   `https` whenever `OBSERVE_COOKIE_SECURE` is `true` (its default --
   "public/secure mode" per the ticket). An **unset** value never raises;
   it is the intended default steady state.
2. **`agent_control/observe_links.py`** (new module) -- the single place
   that turns `OBSERVE_PUBLIC_BASE_URL` + a `run_id` into a link:
   - `is_url_safe_run_id` -- a conservative allowlist regex
     (`^[A-Za-z0-9._:-]{1,128}$`) checked **before** any URL interpolation,
     covering every `run_id` shape this codebase produces
     (`make_run_id`/`make_rlm_root_job_id` in `agent_shared.project_ids`,
     `fix_run_id` in `approval/dispatch_fix.py`) while rejecting whitespace,
     `/`, backticks, brackets/parens, and newlines -- anything that could
     break out of a URL path segment or a Markdown link/code span.
   - `build_observe_session_url` -- `None` if the base URL is unset *or*
     `run_id` fails the check above (fail-closed on both axes, logged at
     `WARNING` for the latter); otherwise
     `{base}/observe/sessions/{quote(run_id)}` (trailing slash on the base
     stripped).
   - `observe_link_line` -- `"Observe: {url}"` or `None`; callers append it
     only when it is not `None` (no relative-path fallback anywhere).
   - `observe_config_warning` / `observe_public_base_url_configured` --
     used for the startup log line and the `/readyz` check below.
3. **Comment-projection integration** (item 2 of the ticket) -- every
   Gitea-comment builder that names a `run_id` now calls `observe_link_line`
   and appends the line only when configured, replacing the previous
   unconditional `` Observe: `/observe/sessions/{run_id}` `` relative-path
   text:
   - `format_invocation_started` (`agent_control/invocation_ack.py`) -- the
     visible started ack posted on webhook accept.
   - `render_session_comment_body`
     (`agent_control/observe/comment_projection.py`) -- the versioned
     session-status comment (T02) patched/posted across the session's
     lifetime.
   - `handoff_invocation_to_session`'s correlation stub
     (`agent_control/nl_invocation_wire.py`) -- the "session created" stub
     posted for bare `@agent` invocations (T07-F08).

   `format_invocation_terminal` (success/failure/blocked) is unchanged --
   out of the ticket's explicit scope (`format_invocation_started` /
   comment projection only).
4. **`/readyz` + startup log** -- `readiness.py`'s `build_readiness_report`
   adds an informational `checks.observe_public_base_url` field
   (`"configured"`/`"unset"`) that never gates the `ready`/`degraded`/
   `not_ready` status; `webhook_server.create_app` logs
   `observe_public_base_url_unset` once at startup when unset, instead of
   per-request (avoids log spam on a valid, permanent steady state).
5. **Gitea `extra_tabs` template** (item 3 of the ticket) --
   `docs/gitea-custom/extra_tabs.tmpl` + `docs/gitea-custom/README.md`:
   - Version-pinned to the live homelab Gitea (`1.26.2`, confirmed via
     `GET /api/v1/version` against `git.ham-sup-lo.com` on 2026-07-21), with
     upstream `templates/repo/header.tmpl` / `models/repo/repo.go`
     checksums recorded for future-upgrade drift detection.
   - A documented template-context spike (source-read, not a live CT100
     install -- see "Explicit non-goals honored") confirming the exact
     `{{template "custom/extra_tabs" .}}` insertion point and that
     `.Repository.OwnerName`/`.Repository.Name` are the correct fields to
     build `/observe/repos/{owner}/{repo}` links from -- explicitly **not**
     the unverified `{{.RepoLink}}` shown in older third-party gists.
   - The shipped `.tmpl` requires a human to substitute a literal
     `OBSERVE_PUBLIC_BASE_URL_PLACEHOLDER` with CT103's actual configured
     value before install (Gitea templates cannot read agent-control-plane's
     environment) and explicitly instructs **not** installing the file at
     all while `OBSERVE_PUBLIC_BASE_URL` is unset -- an absent file is the
     fail-closed default, matching item 1 above.
   - A full install checklist (human, CT100) and an upgrade checklist (for
     future Gitea version bumps) are both in the README.
6. **Tests** -- `tests/test_v9_t06_observe_public_links.py` (35 tests):
   `Settings` validator (unset ok; relative/non-http/path/query rejected;
   http rejected under `OBSERVE_COOKIE_SECURE=true`; http accepted only when
   that flag is explicitly `false`); `observe_links` helpers (safe/unsafe
   `run_id` shapes incl. injection-shaped strings, URL building, trailing-
   slash normalization, config warning presence/absence);
   `format_invocation_started`, `render_session_comment_body`, and the NL
   handoff stub all omit the Observe line when unset and include the exact
   expected absolute link when configured; `/readyz`'s
   `observe_public_base_url` check reflects both states without changing
   the overall status code.

## Explicit non-goals honored

- No live install onto CT100 -- outside this repo's documented SSH surface
  (`.cursor/rules/ssh-ct103-ct104.mdc` covers CT103/CT104 only). The
  template-context spike is a source-level verification against the
  version-pinned upstream Gitea source, not a live browser check; the
  install checklist in `docs/gitea-custom/README.md` records what a human
  with CT100 access must additionally confirm.
- No change to `format_invocation_terminal`, the SSE wire format (T03), the
  five-panel UI (T04), or `observe.sqlite`'s schema (T02) -- this ticket
  only adds an optional link to existing comment/ack text and one new,
  independently-installed Gitea customization file.
- No repo-level Observatory HTML page -- the `extra_tabs` link points at the
  existing `/observe/repos/{owner}/{repo}` JSON route (V6 T03); a repo-level
  HTML session list is not in this ticket's scope.
- `OBSERVE_PUBLIC_BASE_URL` is never defaulted to a LAN/HTTP address, even
  for local dev -- unset is the only "just works without config" state, and
  it means "no Observe links", by design.

## HUMAN checklist (CT100 install; does not block this ticket's Deploy gate)

Mirrors the V9 T05 precedent (OAuth app registration): the human-only step
lives in `docs/gitea-custom/README.md`'s "Install on CT100" section --
finding `$GITEA_CUSTOM`, copying `extra_tabs.tmpl`, substituting the real
`OBSERVE_PUBLIC_BASE_URL` value, restarting Gitea, and confirming the tab
renders. Until that happens, Gitea simply shows no Observatory tab -- the
same fail-closed state as before this ticket; agent-control-plane's own
Observe links (item 3 above) are unaffected either way, since they only
depend on `OBSERVE_PUBLIC_BASE_URL` being set on CT103, not on the Gitea
template being installed.

## Done criteria (after CT103/CT104 deploy-verify)

- `ruff check .` clean, full test suite passing (see "Verification" below)
- CT103 (+CT104) deploy-verify: CI green on the pushed tip, `/readyz` still
  `ok`/`degraded` as before (new `observe_public_base_url` check present),
  no `/observe` route regression
- `OBSERVE_PUBLIC_BASE_URL` left unset in this ticket's deploy (no human
  action required for code Done); Gitea `extra_tabs` install on CT100
  remains an optional human follow-up, tracked but not blocking

## Non-goals

- Agent-driven CT100 filesystem access or Gitea restarts
- Defaulting `OBSERVE_PUBLIC_BASE_URL` to any LAN/HTTP address
- Structured decisions/artifact-disposition rendering (T07) or CI-stream
  ingestion (T08)

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 808 passed
```

New test file: `tests/test_v9_t06_observe_public_links.py` (35 tests).
