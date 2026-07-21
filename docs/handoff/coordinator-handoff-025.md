# Handoff — coordinator-handoff-025

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 025 |
| Date (UTC) | 2026-07-21 |
| Slice / ticket ID | V8 T04 |
| Tip SHA (ACP) | `4c16f5d` |
| Epic | V8 residual QA |
| `stopped_reason` | `waiting_human` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-025.md
ticket: T04
status: WaitingHuman
blocker: none
stopped_reason: waiting_human
human_needed: Gitea OAuth app + CT103 secrets + user-bearer smoke
```

## Slice outcome

- Agent prep only: documented human OAuth registration; config placeholders; unit tests for user bearer / shared token / fail-closed.
- **No** OAuth app created by agent; **no** client secrets invented or committed.
- Callback browser routes deferred until secrets exist (user bearer path already live via `_token_has_repo_read`).
- Slice doc: [docs/slice-v8-t04-observatory-oauth.md](../slice-v8-t04-observatory-oauth.md)

## Evidence pointers

- Unit: `tests/test_v8_t04_observatory_oauth.py`
- Auth: `src/agent_control/observe/auth.py` (unchanged behavior)
- Config keys: `OBSERVE_OAUTH_CLIENT_ID` / `CLIENT_SECRET` / `REDIRECT_URI` in `config.py` + `.env.example`
- HUMAN checklist: section in slice doc

## Decisions the next coordinator must honor

1. Do not mark T04 Done until human completes OAuth app + CT103 `.env` + smoke curl (200 with user bearer, 401 without).
2. Keep `OBSERVE_REQUIRE_AUTH=true`; shared token remains optional.
3. Secrets stay on CT103 only.

## Next coordinator: first actions

1. Wait for human checklist completion (slice doc).
2. After secrets: live smoke on CT103; optional callback scaffolding follow-up if product wants browser login.
3. Record deploy verify; flip T04 → Done in boss-ledger-v8.

## Open risks (one line each)

- Redirect URI mismatch (LAN vs NPM public URL) will break any future callback; human must pick one and match env.
