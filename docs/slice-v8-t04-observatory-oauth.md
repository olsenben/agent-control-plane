# Slice V8 T04 — Real Observatory Gitea OAuth (agent prep)

**Status:** WaitingHuman  
**Epic ticket:** T04  
**Deps:** T03 helpful (not hard-blocked)  
**Handoff:** [coordinator-handoff-025.md](handoff/coordinator-handoff-025.md)

## Goal

Move Observatory off shared-token-only ops: accept a **Gitea user bearer** with repo-read (already gated via `_token_has_repo_read`), keep optional `OBSERVE_SHARED_TOKEN`, fail closed without credentials. Human registers a Gitea OAuth application and places secrets on CT103; agent does not mint apps or invent secrets.

## Already in code (agent)

| Path | Behavior |
|------|----------|
| `Authorization: Bearer <token>` or `X-Gitea-Token` | Required when `OBSERVE_REQUIRE_AUTH=true` (default) |
| `OBSERVE_SHARED_TOKEN` | Optional shared bearer (hmac compare) |
| Else | Gitea `GET /api/v1/repos/{owner}/{repo}` as that token; need `permissions.pull` (or push/admin) |
| Missing token | **401** |
| Bad / no-read token | **403** |

OAuth **authorization-code callback routes** are intentionally not shipped in this prep slice. After the OAuth app exists, operators may use a Gitea user access token / PAT (or future callback) as the bearer above.

## Config keys (no secrets in git)

| Env | Purpose |
|-----|---------|
| `OBSERVE_REQUIRE_AUTH` | Default `true`; do not disable in production |
| `OBSERVE_SHARED_TOKEN` | Optional interim shared gate (still supported) |
| `OBSERVE_OAUTH_CLIENT_ID` | From Gitea OAuth app (CT103 `.env` only) |
| `OBSERVE_OAUTH_CLIENT_SECRET` | From Gitea OAuth app (CT103 `.env` only) |
| `OBSERVE_OAUTH_REDIRECT_URI` | Must match app registration exactly |

Suggested redirect (LAN control-plane):

`http://192.168.4.62:8080/observe/oauth/callback`

Gitea base (homelab): `https://git.ham-sup-lo.com` (`GITEA_BASE_URL`).

## HUMAN checklist (required before Done)

1. **Create Gitea OAuth application** (admin or user with permission): Gitea → **Settings → Applications → Manage OAuth2 Applications → Create**.
2. **Application name:** e.g. `Observatory CT103` (label only).
3. **Redirect URI:** set exactly to `http://192.168.4.62:8080/observe/oauth/callback` (or the public NPM URL you will use; must match `OBSERVE_OAUTH_REDIRECT_URI`).
4. **Copy Client ID + Client Secret** once; store only on CT103 (never commit, never CT104).
5. **On CT103** `/opt/ai-sdlc-lab/agent-control-plane/.env` (or compose env), set:
   - `OBSERVE_REQUIRE_AUTH=true`
   - `OBSERVE_OAUTH_CLIENT_ID=…`
   - `OBSERVE_OAUTH_CLIENT_SECRET=…`
   - `OBSERVE_OAUTH_REDIRECT_URI=http://192.168.4.62:8080/observe/oauth/callback`
   - Keep or clear `OBSERVE_SHARED_TOKEN` as desired (shared path remains valid).
6. **Restart** CT103 control-plane compose so settings reload.
7. **Smoke (user bearer):** obtain a Gitea personal access token (or OAuth access token) for a user with **read** on `ai-sdlc-lab/demo-app`, then:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <USER_TOKEN>" \
  "http://192.168.4.62:8080/observe/repos/ai-sdlc-lab/demo-app"
# expect 200

curl -sS -o /dev/null -w "%{http_code}\n" \
  "http://192.168.4.62:8080/observe/repos/ai-sdlc-lab/demo-app"
# expect 401
```

8. Reply to coordinator with: Client ID present (yes/no), redirect URI used, smoke HTTP codes — **do not paste the client secret or PAT into chat/git**.

## Agent tests (prep)

- `tests/test_v8_t04_observatory_oauth.py` — unauth 401, shared token ok, user bearer with pull ok, no-pull 403.

## Done criteria (after human)

- OAuth app registered + secrets on CT103  
- Observatory accepts user bearer with repo-read  
- Shared-token path still optional  
- Unauth → 401  
- Deploy verify / live smoke recorded  

## Non-goals

- Agent creating OAuth apps or inventing client secrets  
- Disabling `OBSERVE_REQUIRE_AUTH` in production  
- Putting OAuth secrets on CT104  
