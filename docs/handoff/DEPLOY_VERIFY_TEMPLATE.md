# Deploy verification template

**Mandatory between slices.** A ticket is not `Done` until this checklist passes for the tip that will be the baseline of the next slice.

Copy into the slice doc under `## Deploy verification (YYYY-MM-DD)` or keep a dated file  
`docs/handoff/deploy-verify-Txx-YYYYMMDD.md`.

## Identity

| Field | Value |
|-------|-------|
| Ticket ID | |
| Slice doc | |
| Tip SHA (expected) | |
| Date (UTC) | |
| Operator | |

## A. CI / Actions (CT102)

| Check | Result | Evidence |
|-------|--------|----------|
| `test` (or equivalent) green for tip | pass / fail | run # |
| `deploy` (CT103) green for tip | pass / fail / N/A | run # |
| `deploy-ct104` green for tip | pass / fail / N/A | run # |

N/A only when the slice is docs-only or CT103-only (state why).

## B. Host tip pin

| Host | Command / check | Tip SHA | Match? |
|------|-----------------|---------|--------|
| CT103 (`192.168.4.62`) | `git -C /opt/ai-sdlc-lab/agent-control-plane rev-parse HEAD` | | yes / no |
| CT104 (`192.168.4.63`) | same (if worker image/code changed) | | yes / no / N/A |

Use WSL + deploy key per `.cursor/rules/ssh-ct103-ct104.mdc`.

## C. Control-plane health

| Check | Result | Notes |
|-------|--------|-------|
| CT103 `/readyz` (redis + state) | ok / fail | |
| Required compose services up | ok / fail | list if fail |
| Unexpected secret / write-token on CT104 | absent / **fail** | fail closed |

## D. Slice smoke (ticket-specific)

Fill from the ticket's "Deploy smoke" row in [boss-ledger.md](boss-ledger.md).

| Step | Result | Evidence (session/run/issue) |
|------|--------|------------------------------|
| | pass / fail / N/A | |
| | pass / fail / N/A | |

## E. Regression floor (always)

| Check | Result |
|-------|--------|
| No protected `main` mutation by agent path | pass / fail |
| Risk 2 still requires approval + sandbox when exercised | pass / fail / N/A |
| Publish still via CT103 `publish-broker` only | pass / fail / N/A |

## Verdict

```text
DEPLOY_VERIFY: PASS | FAIL
tip: <sha>
next_slice_unblocked: yes | no
blocker: none | <one line>
```

On **FAIL**: set ledger ticket to `Blocked` or keep `In Progress`; do **not** advance `Next ticket`. Write handoff with `stopped_reason: blocker` or `deploy_gate_pending`.
