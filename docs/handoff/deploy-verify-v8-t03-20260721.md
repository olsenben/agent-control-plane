# Deploy verification — V8 T03 mid-SSE token revoke

| Field | Value |
|-------|-------|
| Ticket ID | V8 T03 |
| Slice doc | docs/slice-v8-t03-mid-sse-revoke.md |
| Feature tip | `ab67815` (mid-SSE revoke) |
| Host tip at proof | `d4e2576` (includes `ab67815`) |
| Date (UTC) | 2026-07-21 |
| Operator | Cursor V8 T03 agent |

## A. CI / tip pin

| Check | Result | Evidence |
|-------|--------|----------|
| Feature commit on main | pass | `ab67815` ancestor of `origin/main` |
| CT103 host tip | pass | `d4e2576` |
| Container has `resolve_observe_shared_token` | pass | `HAS_RESOLVE True` |

## B. Control-plane health

| Check | Result |
|-------|--------|
| CT103 `/readyz` | ok (preflight in smoke) |

## C. Slice smoke (T03)

| Step | Result | Evidence |
|------|--------|----------|
| `scripts/_v8_t03_mid_sse_revoke.sh d4e2576` | pass | `V8_T03_MID_SSE_REVOKE_OK`; `SAW_DATA=True ROTATED=True SAW_ERROR=True`; hot-reload file removed after proof |
| Unit | pass | `tests/test_v8_t03_mid_sse_revoke.py` (2 passed locally) |

## D. Method

1. Seed throwaway session `run-v8t03-live` under `ai-sdlc-lab/demo-app`
2. Write `/data/agent-state/.observe_shared_token` (token-v1)
3. Open `GET /api/observe/sessions/.../stream` with Bearer v1
4. After first SSE `data:` frame, rotate file to token-v2
5. Mid-stream re-check emits `event: error` / `forbidden`; no further timeline `id:` frames expected after error
6. Remove hot-reload file (cleanup)

## Verdict

```text
DEPLOY_VERIFY: PASS
tip: d4e2576 (feature ab67815)
next_slice_unblocked: yes
blocker: none
```
