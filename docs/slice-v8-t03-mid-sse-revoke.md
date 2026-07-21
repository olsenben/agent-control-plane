# Slice V8 T03 — Mid-SSE token revoke

**Status:** Done  
**Epic ticket:** V8 T03  
**Deps:** none (disjoint from T01/T02/T04)

## Goal

Prove Observatory SSE drops after shared-token invalidation mid-stream: open stream with a valid `OBSERVE_SHARED_TOKEN` (or hot-reload file), rotate/invalidate mid-stream, stream emits unauthorized error and no further timeline events.

## Implementation

| Piece | Change |
|-------|--------|
| `observe/auth.py` | `resolve_observe_shared_token()` — prefer `<agent_state_root>/.observe_shared_token` when present (hot reload for mid-stream rotation without restart); else env/settings |
| `observe/routes.py` | SSE poll loop reloads `_settings(request)` each tick before auth re-check |
| `tests/test_v8_t03_mid_sse_revoke.py` | File rotate + settings mutate mid-poll |
| `scripts/_v8_t03_mid_sse_revoke.sh` | CT103 live proof: seed session, open SSE, rotate file, assert `event: error` / forbidden |

## Non-goals

- Gitea OAuth app / personal-token UI delete (T04 / optional human path)
- Disabling `OBSERVE_REQUIRE_AUTH`

## Deploy verification

1. Tip pinned on CT103
2. `scripts/_v8_t03_mid_sse_revoke.sh <tip>` → `V8_T03_MID_SSE_REVOKE_OK`
3. Evidence under `docs/handoff/deploy-verify-v8-t03-*.md`
