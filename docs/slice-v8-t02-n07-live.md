# Slice V8 T02 — N07 live (approver revoked before publish)

**Status:** WaitingHuman  
**Date:** 2026-07-21  
**Epic ticket:** V8 T02  
**Deps:** none  

## Goal

Prove publish is denied after a **real Gitea collaborator revoke** of the recorded approver (not a mock), with an `authorization_decision` / `authorization_denied` audit trail, on `ai-sdlc-lab/demo-app` safely.

## Acceptance

| Check | Expected | Result |
|-------|----------|--------|
| Hermetic N07 | `recheck_publish_authorization` denies when approver loses repo write | pass (unit) |
| Publish path | Pre-publish recheck requires live write for recorded approver | pass (code) |
| Live revoke | Bot adds disposable write collaborator → allow → DELETE → deny + audit event | **WaitingHuman** — bot cannot create/manage a disposable human user |
| Safety | Never revoke production approver `olsenben`; no CT104 write tokens | pass |

## Probe findings (CT103 bot)

- Bot has **admin** on `ai-sdlc-lab/demo-app`; collaborator DELETE route reachable (422 on nonexistent user).
- Bot token **lacks** `read:admin` / `write:admin` / `read:user` — cannot list/create users.
- Org has a single member (`olsenben`); collaborators list empty. Revoking `olsenben` is refused by harness.

## Artifacts

| Path | Role |
|------|------|
| `src/agent_control/authorization.py` | Publish recheck requires live approver write |
| `tests/test_qa_v6_wave3.py` | `test_n07_approver_revoked_before_publish` |
| `scripts/_v8_t02_n07_probe.sh` | Capability probe |
| `scripts/_v8_t02_n07_live.sh` | Live allow→revoke→deny harness |
| `docs/handoff/coordinator-handoff-023.md` | Handoff |
| `docs/handoff/evidence/v8-t02-n07-*.txt` | Live/probe evidence |

## Human steps (to reach Done)

1. Create a disposable Gitea user (e.g. `v8-n07-disposable`) — site admin UI or admin API. Do **not** use `olsenben`.
2. Ensure tip with N07 publish write-recheck is deployed on CT103 (this slice commit).
3. From WSL: `DISPOSABLE_APPROVER=v8-n07-disposable bash scripts/_v8_t02_n07_live.sh`
4. Confirm evidence shows `N07_LIVE_VERDICT=PASS` (before=allow, after=deny) and an `agent.authorization_decision` event path.
5. Optionally delete the disposable user when finished.

## Non-goals

- Do not revoke production approver or org owner.
- Do not put human PATs on CT104.
- Do not edit DUR soak or Observatory OAuth app code.
