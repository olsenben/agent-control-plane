# Handoff -- coordinator-handoff-028

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 028 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T05 |
| Tip SHA (ACP) | `ab2f7ef` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-028.md
ticket: T05
status: Deploy gate
tip_sha: ab2f7ef
tests: 742 passed
ruff: All checks passed!
blocker: none (OAuth login/callback fail-closed 503 until human registers a
  Gitea OAuth app -- same human step V8 T04 already documented; not a
  blocker for this ticket's Done criteria, which are code + tests + deploy
  verify, not a live human-supplied OAuth secret)
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- Gitea OAuth session shell (`agent_control/observe/oauth.py` +
  `agent_control/observe/session_store.py`): `/observe/oauth/login` (fails
  closed 503 when `OBSERVE_OAUTH_CLIENT_ID`/`_CLIENT_SECRET`/`_REDIRECT_URI`
  are unset; otherwise mints a single-use, TTL-bound `state` bound to an
  HttpOnly cookie and redirects to Gitea's authorize endpoint),
  `/observe/oauth/callback` (validates state==cookie==server-record,
  exchanges the code, fetches the Gitea user, mints a fresh
  `secrets.token_urlsafe` session id -- never derived from any client input
  -- and sets the session cookie), `/observe/oauth/logout` (deletes the
  server-side row + clears the cookie). Both session and state cookies are
  HttpOnly + Secure (default; `OBSERVE_COOKIE_SECURE` override for
  plain-HTTP dev) + SameSite=Lax.
- Auth response matrix (`agent_control/observe/auth.py`): identity
  resolution (`resolve_observe_identity`/`require_observe_identity`, 401 or
  302-to-login via `Accept: text/html` sniffing) is now a separate step from
  repo-read authorization (`authorize_repo_read`, 403 denied / 503
  Gitea-unreachable). `_token_has_repo_read` raises `GiteaUnavailableError`
  (-> 503) on transport errors, Gitea 5xx, or a non-JSON 2xx body; a
  reachable Gitea denial is unchanged (403). `OBSERVE_SHARED_TOKEN` keeps
  working exactly as before, independent of OAuth configuration state.
- Confused-deputy fix (`agent_control/observe/routes.py`):
  `/sessions/{run_id}/{events,artifacts,stream}` now resolve the
  authorization-relevant project from the session-index file (falling back
  to the V9 T02 `observe.sqlite` projection) rather than trusting the
  client-supplied `project` query parameter, which is now only a
  logged-on-mismatch hint.
- `/api/observe/v1/*` versioned mount added; the legacy unversioned
  `/api/observe/*` prefix is kept as an identical alias (same handler
  functions registered on both routers via `add_api_route`).
- `ENFORCE_PUBLIC_SURFACE_RESTRICTION` behavior unchanged (already exempted
  `/observe` + `/api/observe`); added regression tests locking in that
  `/docs`, `/redoc`, `/openapi.json` stay 404 and that oauth/observe stay
  reachable (subject to their own auth) when the flag is on.
- ADR-0029 accepted; slice doc
  [docs/slice-v9-t05-gitea-oauth-shell.md](../slice-v9-t05-gitea-oauth-shell.md)
  (carries forward the V8 T04 human OAuth-app checklist -- no secrets
  invented, none placed in this repo's `.env`).
- New tests: `tests/test_v9_t05_oauth_shell.py` (31 tests) covering the full
  response matrix, SSE authorize-before-open (never a 200 + streamed error
  for a denied caller), shared-token coexistence, versioned-mount parity,
  the confused-deputy attack + legitimate-match cases, unknown-run 404
  ordering (after the 401 check, never before), public-surface-restriction
  regression, and the full OAuth flow (fail-closed unconfigured,
  authorize-URL/state-cookie shape, open-redirect guard, successful login,
  state replay rejection, state/cookie mismatch, Gitea-unavailable/rejected
  mid-exchange, `error=` denial, logout, forged-cookie rejection, distinct
  session ids per login).
- `ruff check .` clean; full suite `742 passed` (was 711 before this ticket;
  +31).
- Committed on `main` (`ab2f7ef`); push pending this handoff's ledger commit
  (both go up together, matching the T02 wave pattern).

## Explicit non-goals honored

- No Redis id-notify / Last-Event-ID SSE upgrade (T03) -- the existing V6 T03
  polling-loop SSE generator's re-check-on-tick logic is unchanged besides
  the identity/project ordering fix.
- No Jinja/HTMX five-panel UI (T04) -- the one HTML page route's inline
  template is untouched besides its auth ordering and its links now pointing
  at `/api/observe/v1/...`.
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` (T06).
- No Gitea OAuth application created, no client secret invented or placed in
  this repo's `.env` -- `/observe/oauth/login` and `/observe/oauth/callback`
  both verified to return 503 in this state (see tests
  `test_login_fails_closed_when_unconfigured` /
  `test_callback_fails_closed_when_unconfigured`).

## Evidence pointers

- Code: `src/agent_control/observe/auth.py`,
  `src/agent_control/observe/oauth.py`,
  `src/agent_control/observe/session_store.py`,
  `src/agent_control/observe/routes.py` (diff),
  `src/agent_control/observe/store.py` (diff: `get_project_for_run`),
  `src/agent_control/webhook_server.py` (diff: `app.state.observe_sessions`
  + allowlist comment),
  `src/agent_control/config.py` (diff: `observe_oauth_scope`,
  `observe_cookie_secure`, `observe_session_ttl_seconds`,
  `observe_oauth_state_ttl_seconds`, `observe_sessions_db_path`)
- Tests: `tests/test_v9_t05_oauth_shell.py`
- Docs: ADR-0029, `docs/slice-v9-t05-gitea-oauth-shell.md`, `.env.example`
  (diff)

## Decisions the next coordinator must honor

1. `require_observe_identity` (401/redirect) must always run before any
   resource-existence check (e.g. resolving a `run_id` to a project) --
   T03/T04 must preserve this ordering in any new route so unauthenticated
   callers never learn whether a resource exists.
2. Repo derivation for any future `run_id`-keyed route must go through
   `routes._resolve_canonical_project` (or an equivalent server-side lookup)
   -- never trust a client-supplied `project`/`repo` field alone when a
   `run_id` is also present.
3. New Observatory HTTP surface should be added under `/api/observe/v1/*`
   going forward; the unversioned `/api/observe/*` alias exists only for
   back-compat and should not gain new endpoints.
4. `GiteaUnavailableError` -> 503 is the established pattern for "the
   permission check itself could not be performed" everywhere Gitea is
   called synchronously from a request path; do not collapse it back into a
   generic `except Exception: return False` in future auth code.
5. `ObserveSessionStore` (`observe_sessions.sqlite`) is a separate file from
   `ObserveStore` (`observe.sqlite`, T02) by design (different lifecycle/
   retention) -- do not merge their schemas.

## Next coordinator: first actions

1. `git push origin main` (this handoff + ledger commit, on top of `ab2f7ef`)
   so CT102 Actions runs per the homelab deploy pattern.
2. Deploy-verify on CT103 (+CT104 if applicable): confirm CI green on the
   pushed tip, `/readyz` still ok, and a smoke of
   `/observe/oauth/login` -> 503 (secrets still unset) +
   `/observe/repos/<allowed-repo>` -> 401 unauth, matching the T01/T02
   pattern, before flipping T05 to Done.
3. If/when a human completes the OAuth-app checklist in
   `docs/slice-v9-t05-gitea-oauth-shell.md`, re-smoke the live login/callback
   flow and record the result in the deploy-verify doc; this is not required
   to flip T05 to Done (Done criteria for the *ticket* are code+tests+deploy
   verify) but should be tracked as an open item if the human step is still
   outstanding at that point.
4. Start T03 (Protected SSE subscribe-first + Redis id-notify +
   Last-Event-ID) per the epic spine (`T01 -> T02 -> T05 -> T03 -> T04 ->
   T06 -> T07 || T08`); T03 should read through `require_observe_identity`/
   `authorize_repo_read` rather than re-deriving auth, and through
   `ObserveStore`'s pagination helpers per T02's decision log.

## Open risks (one line each)

- OAuth login/callback are untested against a *live* Gitea instance in this
  ticket (all Gitea calls are mocked in `test_v9_t05_oauth_shell.py`); the
  deploy-verify step should include a live smoke once a human supplies real
  OAuth app secrets, per the slice doc's checklist.
- `observe_sessions.sqlite` has no pruning job for expired-but-never-read
  rows (TTL is enforced on read, not swept proactively) -- non-issue at
  homelab scale today, called out in ADR-0029 follow-ups for future
  revisit if traffic grows.
