# Slice V9 T05 -- Gitea OAuth session shell + protected observe router

**Status:** Done -- 2026-07-22 (deploy verify [deploy-verify-v9-t05-20260722.md](handoff/deploy-verify-v9-t05-20260722.md), tip `1f71bf6`)
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Handoff:** [coordinator-handoff-028.md](handoff/coordinator-handoff-028.md)
**ADR:** [0029-observatory-oauth-session-shell.md](adr/0029-observatory-oauth-session-shell.md)
**Depends on:** T02 (done, tip `6a67233`)
**Supersedes (checklist only, not code):** [slice-v8-t04-observatory-oauth.md](slice-v8-t04-observatory-oauth.md)

## Goal

Add a browser-facing Gitea OAuth login/callback/logout shell in front of the
Observatory, and mount the protected `/api/observe/v1/*` router behind it,
implementing this auth response matrix:

| Caller state | Response |
|---|---|
| Unauthenticated, browser (`Accept: text/html`) | 302 -> `/observe/oauth/login?next=...` |
| Unauthenticated, API/SSE | 401 JSON |
| Authenticated, no repo-read | 403 |
| Gitea permission service unreachable/erroring | 503 (never 403) |
| SSE | authorized **before** the stream opens; never a 200 + streamed error |

## What shipped

1. **Auth split** (`agent_control/observe/auth.py`):
   `resolve_observe_identity` -> `require_observe_identity` (401/redirect,
   does not need to know the target project) and `authorize_repo_read`
   (403/503, needs the project). `require_observe_repo_read` is kept as a
   convenience wrapper of both for routes whose project is already trusted
   from path params. Identity now includes an `observe_session` cookie
   resolved through `ObserveSessionStore`, in addition to the existing
   header-bearer and `OBSERVE_SHARED_TOKEN` paths (both unchanged).
   `_wants_html` (Accept-header sniffing) decides redirect-vs-401 without a
   per-route flag -- `text/html` -> redirect, everything else (including
   `text/event-stream`) -> 401 JSON.
2. **503 vs 403** -- `_token_has_repo_read` now raises `GiteaUnavailableError`
   on transport errors, Gitea 5xx, and non-JSON 2xx responses; the caller
   maps that to 503. A reachable Gitea that says no (404/401/403/no
   pull-push-admin) is unchanged: 403.
3. **Session store** (`agent_control/observe/session_store.py`):
   `ObserveSessionStore` — sqlite `observe_oauth_state` (single-use,
   TTL-bound CSRF binding) and `observe_session` (TTL-bound login sessions;
   `session_id` always freshly minted post-authentication, never accepted
   from client input -- the session-fixation defense). Same WAL/
   `busy_timeout`/`BEGIN IMMEDIATE` pattern as `ObserveStore` (T02).
4. **OAuth routes** (`agent_control/observe/oauth.py`), mounted at
   `/observe/oauth/{login,callback,logout}`:
   - `login`: fails closed (503) if `OBSERVE_OAUTH_CLIENT_ID`/
     `_CLIENT_SECRET`/`_REDIRECT_URI` are unset. Otherwise mints a `state`,
     stores it server-side with a sanitized `next` redirect target
     (open-redirect guard: only same-app relative paths), sets an HttpOnly/
     Secure/SameSite=Lax `observe_oauth_state` cookie, redirects to Gitea's
     `/login/oauth/authorize`.
   - `callback`: requires the query `state` to match both the cookie *and* a
     non-expired, not-yet-used server record (single-use -- replay is
     rejected); exchanges the code at `/login/oauth/access_token`, fetches
     `/api/v1/user`, mints a fresh session id, sets the HttpOnly/Secure/
     SameSite=Lax `observe_session` cookie, redirects to the original `next`.
     Gitea-unreachable -> 503; Gitea-rejected-code/token -> 401;
     `error=` query param (user denied) -> 400.
   - `logout`: deletes the server-side session row and clears the cookie.
5. **Confused-deputy fix for `run_id`-keyed routes**
   (`agent_control/observe/routes.py`): `_resolve_canonical_project` derives
   the repo from the session-index file under `agent_state_root`, falling
   back to `ObserveStore.get_project_for_run` (T02 projection) if the run was
   pruned from the live index. The `project` query parameter on
   `/sessions/{run_id}/{events,artifacts,stream}` is now an optional,
   non-authoritative *hint* (mismatches are logged, never trusted) -- the
   authorize call and the data fetch always use the same server-derived
   value, closing the gap where a caller with read on repo A could supply
   `project=A` while reading a `run_id` that actually belongs to repo B.
6. **Versioned mount**: `/api/observe/v1/*` registered as the primary prefix;
   the pre-existing unversioned `/api/observe/*` stays as an identical alias
   built from the same endpoint functions via `router.add_api_route` (one
   implementation, two mounts -- see ADR-0029 point 8).
7. **`ENFORCE_PUBLIC_SURFACE_RESTRICTION`**: no functional change -- `/observe`
   and `/api/observe` (including the new `/v1` prefix and the new oauth
   routes) were already exempt from the restriction because they enforce
   their own auth; `/docs`, `/redoc`, `/openapi.json` were already outside
   both allowlists. New regression tests lock this in.
8. **Config** (`agent_control/config.py`): `OBSERVE_OAUTH_SCOPE` (optional,
   default empty -> omitted from the authorize URL), `OBSERVE_COOKIE_SECURE`
   (default `true`), `OBSERVE_SESSION_TTL_SECONDS` (default 43200 = 12h),
   `OBSERVE_OAUTH_STATE_TTL_SECONDS` (default 600 = 10m).
   `OBSERVE_OAUTH_CLIENT_ID`/`_CLIENT_SECRET`/`_REDIRECT_URI` already existed
   from V8 T04 prep; unchanged here.
9. **Tests** -- `tests/test_v9_t05_oauth_shell.py` (31 tests): full response
   matrix (redirect/401/403/503), SSE authorize-before-open, shared-token
   coexistence, versioned-mount parity, confused-deputy repo derivation
   (attack + legitimate-match cases), unknown-run 404 ordering,
   public-surface-restriction regression, and the full OAuth flow
   (fail-closed unconfigured, authorize-URL + state cookie shape, open-redirect
   guard, successful login -> session cookie -> authorized repo access, state
   replay rejection, state/cookie mismatch, Gitea-unavailable/rejected during
   exchange, error-param denial, logout, forged-cookie rejection, distinct
   session ids across logins).

## Explicit non-goals honored

- No Redis id-notify / Last-Event-ID SSE upgrade (T03) -- the existing V6 T03
  polling-loop SSE generator is unchanged except for the identity/project
  resolution ordering fix.
- No Jinja/HTMX five-panel UI (T04) -- the one HTML page route
  (`/observe/sessions/{run_id}`) is the pre-existing inline-HTML page, only
  its auth ordering and its embedded links (now pointing at
  `/api/observe/v1/...`) changed.
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` (T06).
- **No Gitea OAuth application was created and no client secret was
  invented.** `OBSERVE_OAUTH_CLIENT_ID`/`_CLIENT_SECRET`/`_REDIRECT_URI`
  remain unset in this repo's `.env`; `/observe/oauth/login` and
  `/observe/oauth/callback` both return 503 until a human completes the
  checklist below (same checklist V8 T04 already documented -- this ticket's
  callback code is what actually consumes those secrets once supplied).

## HUMAN checklist (unchanged from V8 T04; required before OAuth login works)

1. **Create a Gitea OAuth application**: Gitea -> **Settings -> Applications
   -> Manage OAuth2 Applications -> Create**.
2. **Application name**: e.g. `Observatory CT103` (label only).
3. **Redirect URI**: set exactly to
   `http://192.168.4.62:8080/observe/oauth/callback` (or the public NPM URL
   you will use); it must match `OBSERVE_OAUTH_REDIRECT_URI` exactly,
   including scheme/host/port/path.
4. **Copy Client ID + Client Secret** once; store only on CT103, never CT104,
   never in git.
5. **On CT103** `/opt/ai-sdlc-lab/agent-control-plane/.env` (or compose env):
   - `OBSERVE_REQUIRE_AUTH=true`
   - `OBSERVE_OAUTH_CLIENT_ID=...`
   - `OBSERVE_OAUTH_CLIENT_SECRET=...`
   - `OBSERVE_OAUTH_REDIRECT_URI=http://192.168.4.62:8080/observe/oauth/callback`
   - Keep or clear `OBSERVE_SHARED_TOKEN` as desired (still supported).
6. **Restart** the CT103 control-plane compose service so settings reload.
7. **Smoke** (browser): open `http://192.168.4.62:8080/observe/oauth/login`,
   complete the Gitea authorize prompt, confirm you land back on
   `/observe/...` with an `observe_session` cookie set (DevTools -> Application
   -> Cookies: `HttpOnly`, `Secure`, `SameSite=Lax`).
8. **Smoke** (unauth): `curl -sS -o /dev/null -w "%{http_code}\n"
   http://192.168.4.62:8080/observe/repos/ai-sdlc-lab/demo-app` -> expect
   `401`.
9. Reply to coordinator with: Client ID present (yes/no), redirect URI used,
   login smoke result, unauth smoke code -- **never paste the client secret,
   PAT, or session cookie value into chat/git.**

## Done criteria (after human)

- OAuth app registered + secrets on CT103
- Browser login completes and sets a session cookie meeting the matrix above
- Shared-token path still optional and unaffected
- Unauth UI redirects, unauth API/SSE 401, no-repo-read 403, Gitea-down 503
- Deploy verify / live smoke recorded on CT103 (+CT104 if applicable)

## Non-goals

- Agent creating OAuth apps or inventing client secrets
- Disabling `OBSERVE_REQUIRE_AUTH` in production
- Putting OAuth secrets on CT104
- Session/state row pruning job (TTL-on-read only; see ADR-0029 follow-ups)

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 742 passed
```

New test file: `tests/test_v9_t05_oauth_shell.py` (31 tests).
