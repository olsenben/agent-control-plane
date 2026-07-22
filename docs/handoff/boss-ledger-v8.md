# Boss ledger — V8 residual QA (V6 deferred)

Epic supervisor state for closing the **explicitly deferred** items from [qa-v6-ledger.md](qa-v6-ledger.md). Prior epic: [boss-ledger-v7.md](boss-ledger-v7.md).

| Field | Value |
|-------|-------|
| **Epic name** | V8 — Residual QA (DUR soak, live auth revoke, Observatory OAuth) |
| **Origin** | QA V6 deferred residual (SIGNED OFF tip `28292c0`) |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Status doc** | This ledger + per-slice `docs/slice-v8-*.md` + [qa-v8-ledger.md](qa-v8-ledger.md) |
| **Integration branch** | `main` |
| **Epic status** | in progress (2/4 Done; T02+T04 WaitingHuman) |
| **Tickets done (count)** | 2 / 4 |
| **Next ticket** | T02 + T04 (human) |
| **Latest handoff** | [coordinator-handoff-025.md](coordinator-handoff-025.md) |
| **Coordinator waves completed** | 1 (parallel automatable) |
| **Last boss action** | 2026-07-21 — T01+T03 Done; T02+T04 WaitingHuman; tip ~`2471b31` |
| **Lanes** | main only (serial; live-auth tickets may pause for human) |
| **Environment constraints** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; CT102 CI; **no CT104 Gitea write tokens**; live OAuth / secret minting may require human |

## Done condition

All tickets **T01–T04** `Done` with deploy verify (or explicit N/A + evidence) PASS. QA V8 ledger SIGNED OFF. Residual list in [qa-v6-ledger.md](qa-v6-ledger.md) marked closed with pointers here.

## Already signed off (do not re-open)

- V6 epic + QA V6 SIGNED OFF — reopen **only** the four deferred rows below
- V7 complete tip `573a777` / docs tip `c274c07` — bake-off out of scope

## Remaining tickets (dependency order)

Status: `Todo` | `In Progress` | `Deploy gate` | `Done` | `Blocked` | `WaitingHuman`

| ID | Slice | Deps | Deploy / proof smoke (minimum) | Agent vs human | Status |
|----|-------|------|--------------------------------|----------------|--------|
| **T01** | **Homelab DUR soak / restart** — bounce CT103 control-plane (+ optional CT104 workers); prove ledger sequence, projections, budget keys, `/readyz` survive | — | Scripted restart soak; before/after sequence continuity; no silent truncation | **Mostly agent** (~85%). Human: approve disruptive restart window if prod-ish traffic matters | Done |
| **T02** | **N07 live** — approver revoked before publish (real Gitea permission change, not mock) | — | Publish denied after revoke; audit event / authorization_denied; demo-app safe | **Split** (~50/50). Agent: harness + API revoke if bot is repo admin. **Human:** supply/approve a disposable human approver account (or perform UI revoke) when bot cannot manage that principal | WaitingHuman |
| **T03** | **Mid-SSE token revoke** — Observatory SSE drops after credential invalidation mid-stream | — | Live SSE opens; token revoked/rotated; stream ends unauthorized; no further events | **Mostly agent** (~80%). Preferred path: rotate `OBSERVE_SHARED_TOKEN` mid-stream. Human only if proving **personal OAuth token** deletion via Gitea UI | Done |
| **T04** | **Real Observatory Gitea OAuth** — browser/user OAuth (or documented Gitea OAuth app) instead of shared-token-only gate | T03 helpful | OAuth app configured; Observatory accepts user bearer with repo-read; shared-token path still optional; unauth → 401 | **Human-gated** (~60% human). **Human:** create Gitea OAuth application + client secret + redirect URL; put secrets on CT103. Agent: code/wiring, fail-closed tests, deploy config docs, smoke with provided credentials | WaitingHuman |

### Parallelism policy

- Default **serial** T01 → T02 → T03 → T04.
- T01 may run anytime (ops soak).
- T02 and T04 may sit in `WaitingHuman` without blocking T01/T03 if the boss explicitly allows a disjoint wave (still one deploy-verify owner).

### Explicit non-goals

- Do not reopen fixed F-01–F-12 or signed QA-T01–T08 except where these residuals require it.
- Do not put human PATs on CT104.
- Do not disable `OBSERVE_REQUIRE_AUTH` in production.
- Do not treat this epic as a product feature epic (V7 bake-off stays closed).

## Agent vs human — summary

| Who | Owns |
|-----|------|
| **Agent** | Soak/restart scripts; unit + integration tests; CT103/CT104 SSH verify; Actions green; shared-token mid-SSE proof; harnesses; docs/evidence; ledger/handoffs |
| **You (human)** | Approve restart windows; create/own disposable Gitea human user for N07 if needed; create Gitea OAuth app + secrets for T04; optional UI revoke / personal-token delete when API path insufficient; final product sign-off judgment |

**Rough effort split for the whole epic:** ~60–70% agent-automatable proof/automation, ~30–40% human secrets, accounts, and disruptive-ops consent.

## Wave log

| Wave | Date (UTC) | Handoff file | Next ticket | Notes |
|------|------------|--------------|-------------|-------|
| 0 | 2026-07-21 | — | T01 | Epic opened from QA V6 deferred list; baseline tip `c274c07` |
| 1 | 2026-07-21 | 022–025 | T02+T04 human | T01 Done; T03 Done; T02/T04 WaitingHuman; tip `2471b31` |

## Boss prompt skeleton

```text
EPIC: V8 residual QA — finish T01–T04 per docs/handoff/boss-ledger-v8.md.

RULES:
1. Orient from this ledger only; one slice per wave (unless WaitingHuman + disjoint allowed).
2. DEPLOY_VERIFY or explicit live-proof evidence before Done.
3. Stop and set WaitingHuman when OAuth app / human account / restart window is required.
4. Environment: CT103 192.168.4.62 / CT104 192.168.4.63; WSL SSH deploy key.
```
