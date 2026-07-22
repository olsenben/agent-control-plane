---
id: ADR-0029
title: Observatory OAuth session shell with 503-vs-403 permission-check distinction
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_control/observe/auth.py"
    - "src/agent_control/observe/oauth.py"
    - "src/agent_control/observe/session_store.py"
    - "src/agent_control/observe/routes.py"
    - "src/agent_control/webhook_server.py"
    - "src/agent_control/config.py"
  symbols:
    - require_observe_identity
    - authorize_repo_read
    - resolve_observe_identity
    - ObserveSessionStore
    - observe_oauth_router
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

V8 T04 shipped the Observatory's fail-closed *bearer-token* auth path (shared
token, Gitea user PAT/OAuth-access-token-as-bearer) but deliberately did not
ship browser OAuth login/callback routes -- a human still had to hand-carry a
PAT. V9 T05 adds that browser-facing shell: `/observe/oauth/{login,callback,
logout}`, a session cookie, and a mount of the protected observe surface at a
versioned `/api/observe/v1/*` prefix. Four properties are non-negotiable per
the epic plan and this ticket's acceptance criteria:

1. Unauthenticated browser navigation must redirect to login; unauthenticated
   API/SSE callers must get 401 JSON -- the same underlying check must serve
   both without duplicating auth logic per route.
2. "Gitea is unreachable while we try to check a permission" must be
   distinguishable from "Gitea was reached and said no" -- conflating the two
   as a blanket 403 hides an operational outage behind a security denial and
   makes on-call diagnosis harder for no benefit (a legitimate caller during
   a Gitea outage should see 503 and retry, not be told they lack access).
3. The OAuth login flow must not be vulnerable to state replay / login-CSRF /
   session fixation, and must fail closed (503, not a degraded/insecure
   fallback) when `OBSERVE_OAUTH_CLIENT_ID`/`_SECRET`/`_REDIRECT_URI` are not
   configured -- this agent does not mint Gitea OAuth applications or invent
   client secrets.
4. Routes keyed by `run_id` (events/artifacts/stream) must derive the
   authorization-relevant repo from a server-side record, not a
   client-supplied `project` query parameter alone, or a caller with read
   access to repo A could supply `project=A` while actually reading a
   `run_id` that belongs to repo B (confused-deputy).

# Decision

1. **Identity resolution is split from repo-read authorization.**
   `resolve_observe_identity` finds *some* credential (header bearer against
   `OBSERVE_SHARED_TOKEN`, a plain Gitea bearer/PAT, or an
   `observe_session` cookie resolved through `ObserveSessionStore`) without
   ever calling Gitea. `require_observe_identity` wraps that with the
   401-or-redirect decision. `authorize_repo_read` is a separate step that
   takes an already-resolved identity plus an already-resolved project and
   makes the Gitea repo-read call. Routes that already know their project
   from a trusted source (path params) call the combined
   `require_observe_repo_read` convenience wrapper; routes keyed by `run_id`
   call the two steps separately so identity is checked *before* the run_id
   is resolved to a project -- an unauthenticated caller gets 401/redirect
   regardless of whether the run_id exists, never a 404 that would leak
   resource existence to an anonymous caller.
2. **Content negotiation, not route registration, decides redirect vs 401.**
   `_wants_html` checks for `text/html` in `Accept`. A real browser
   navigating to any Observatory page sends that header; curl/httpx smoke
   checks, `EventSource` (`Accept: text/event-stream`), and JSON API callers
   do not. This lets the JSON-returning "UI-tagged" route
   (`/observe/repos/{owner}/{repo}`, already tested since V6 T03 to return
   401 without a browser `Accept` header) and the true HTML page route
   (`/observe/sessions/{run_id}`) share one auth dependency correctly without
   a per-route flag, and guarantees SSE always gets 401 JSON as required.
3. **503 is a distinct outcome from 403 for the Gitea repo-read check.**
   `_token_has_repo_read` raises `GiteaUnavailableError` (mapped to 503 by
   the caller) on transport-level `httpx.HTTPError` (connect/timeout/etc.),
   any Gitea 5xx response, and a non-JSON 2xx response (Gitea returning
   something we cannot parse is itself an unavailability signal, not a
   permission signal). A reachable Gitea returning 404/401/403/permissions
   without `pull`/`push`/`admin` is "checked and denied" -- 403, unchanged
   from V8 T04's behavior for that case.
4. **Session-fixation and OAuth-state defenses, in `session_store.py`.**
   `observe_session.session_id` is minted with `secrets.token_urlsafe(32)`
   only inside `create_session`, called only after a successful Gitea code
   exchange *and* user-profile fetch in `oauth.py` -- never accepted from a
   query param, form field, or pre-existing cookie at any stage. The OAuth
   `state` value is bound to both a short-lived (`OBSERVE_OAUTH_STATE_TTL_SECONDS`,
   default 600s), single-use (`consume_state` marks-and-checks atomically in
   one `BEGIN IMMEDIATE` transaction) server-side record *and* an HttpOnly
   cookie; the callback only proceeds when the query parameter, the cookie,
   and the server record all agree (`hmac.compare_digest`). A captured
   state+cookie pair is useless after first use (replay is rejected), and a
   forged/guessed session cookie value resolves to no session row, falling
   through to the normal 401/redirect path.
5. **Fail-closed OAuth configuration, no invented secrets.** Both
   `/observe/oauth/login` and `/observe/oauth/callback` return 503 immediately
   when `OBSERVE_OAUTH_CLIENT_ID`/`OBSERVE_OAUTH_CLIENT_SECRET`/
   `OBSERVE_OAUTH_REDIRECT_URI` are not all set -- there is no reduced-security
   fallback path. This agent does not create Gitea OAuth applications; the
   human checklist for registering one and placing secrets on CT103 lives in
   `docs/slice-v9-t05-gitea-oauth-shell.md` (supersedes the V8 T04 prep doc's
   checklist -- same steps, now consumed by working callback code instead of
   a PAT-only interim path). `OBSERVE_SHARED_TOKEN` remains fully supported
   as the ops escape hatch regardless of OAuth configuration state.
6. **Cookies: HttpOnly + configurable-Secure + SameSite=Lax.** Both the
   `observe_oauth_state` and `observe_session` cookies are always `HttpOnly`
   (no JS access) and `SameSite=Lax` (Lax, not Strict, because Strict would
   drop the cookie on the top-level GET navigation the browser makes when
   Gitea redirects back to `/observe/oauth/callback`, breaking the flow
   entirely -- Lax still blocks the cookie on cross-site subrequests/POSTs,
   which is what matters for CSRF). `Secure` defaults on
   (`Settings.observe_cookie_secure` / `OBSERVE_COOKIE_SECURE`, default
   `true`) and should only be disabled for plain-HTTP local dev, never in
   production behind the homelab's TLS-terminating reverse proxy.
7. **Repo derivation for `run_id`-keyed routes never trusts the client alone.**
   `routes._resolve_canonical_project` resolves the project from the
   session-index file (`agent_state_root/projects/*/*/sessions/by_run_id/
   {run_id}.json`, ground truth for where a session was actually written) and
   falls back to `ObserveStore.get_project_for_run` (the V9 T02 projection,
   for runs pruned from the live index but already projected). A
   client-supplied `project` query parameter is accepted only as a
   diagnostic hint (logged on mismatch); it is never the value used for the
   authorize call or the data fetch. `/observe/repos/{owner}/{repo}` is
   exempt from this (the owner/repo *are* the trusted input there -- there is
   no `run_id` to derive a canonical value from).
8. **`/api/observe/v1/*` is the versioned mount; the legacy unversioned
   `/api/observe/*` prefix stays as an identical alias.** Both routers are
   built from the exact same endpoint functions via
   `APIRouter.add_api_route`, so there is exactly one implementation to keep
   correct, not two code paths that can drift.
9. **`ENFORCE_PUBLIC_SURFACE_RESTRICTION`'s allowlist is unchanged in
   substance.** The middleware in `webhook_server.py` already treated any
   path under `/observe` or `/api/observe` as exempt from the
   `PUBLIC_ALLOWED_PATHS`-only restriction, because every one of those routes
   enforces its own auth -- exposing the *path* is not exposing the *data*.
   This ticket adds oauth login/callback/logout under that same `/observe`
   prefix (no middleware change required) and adds regression tests that
   FastAPI's auto-generated `/docs`, `/redoc`, `/openapi.json` -- which match
   neither allowlist -- stay 404 when the flag is on.

# Consequences

- Positive: on-call operators see 503 (retry-able, "something's down") instead
  of 403 ("you're not allowed") when Gitea itself is the problem, which is
  the more actionable signal and matches how the rest of this codebase
  already treats upstream-unavailable vs upstream-denied (e.g.
  `readiness.py`'s strict/non-strict split).
- Positive: no second auth implementation for HTML vs JSON/SSE routes to keep
  in sync -- one content-negotiation check.
- Negative: `ObserveSessionStore` is a second sqlite file
  (`observe_sessions.sqlite`) alongside `observe.sqlite` (V9 T02) under
  `agent_state_root/observe/`; acceptable given the different lifecycle
  (session/state rows are transient, TTL-bounded; the T02 projection is a
  durable display cache) but is one more file for `agentctl`/backup tooling
  to be aware of if a future ticket adds Observatory backup/restore.
- Negative: session tokens (Gitea OAuth access tokens) are stored in
  plaintext in `observe_sessions.sqlite` on CT103 to make the subsequent
  per-request Gitea repo-read check possible; this is the same trust
  boundary the existing `GITEA_BOT_TOKEN`/`.env` secrets already live inside
  (CT103-only, never CT104), not a new one, but is called out explicitly
  here since it is now also true of *user* tokens, not just the bot token.
- Follow-up: T03 (protected SSE + Redis id-notify) and T04 (five-panel UI)
  should reuse `require_observe_identity`/`authorize_repo_read` rather than
  re-deriving auth, and should keep using `/api/observe/v1/*` for anything
  new so the unversioned alias can eventually be deprecated without a
  breaking change to already-shipped UI.
- Follow-up: no session/state row pruning job exists yet beyond
  TTL-on-read (`get_session` deletes its own row once expired,
  `consume_state` refuses expired rows); a long-idle `observe_sessions.sqlite`
  could accumulate expired-but-never-read rows. Homelab scale makes this a
  non-issue today; revisit if T06+ traffic grows meaningfully.
