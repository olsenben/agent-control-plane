# Boss ledger — V9 Agent Observatory (approved plan gap-closure)

Epic supervisor state. Prior: [boss-ledger-v8.md](boss-ledger-v8.md) (residual QA; T02+T04 WaitingHuman). Plan: `.cursor/plans/v6_agent_observatory_epic_2ab66432.plan.md` (numbered V9 — homelab V6 already used).

| Field | Value |
|-------|-------|
| **Epic name** | V9 — Agent Observatory (safe-display, projection, OAuth UI, SSE race, panels) |
| **Baseline tip** | `2471b31` |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Integration branch** | `main` |
| **Epic status** | in progress |
| **Tickets done** | 0 / 8 |
| **Next ticket** | T01 |
| **Latest handoff** | — |
| **Lanes** | main only |
| **Env** | WSL SSH; CT103 `192.168.4.62` / CT104 `192.168.4.63`; `docker compose exec -T … </dev/null` |

## Spine (parallelism)

```text
T01 → T02 → T05 → T03 → T04 → T06 → T07 ∥ T08
```

Only **T07 ∥ T08** may run in parallel (after T03 Done).

## Tickets

| ID | Slice | Deps | Status | Tip |
|----|-------|------|--------|-----|
| **T01** | observe_event.v1 + safe-display + producer inventory | — | Todo | |
| **T02** | observe.sqlite idempotent display-safe projection; fail-open async | T01 | Todo | |
| **T05** | Gitea OAuth shell + 401/redirect/403/503; mount protected routes | T02 | Todo | |
| **T03** | Protected SSE subscribe-first + Redis id-notify + Last-Event-ID | T05 | Todo | |
| **T04** | Jinja+HTMX five-panel UI; text-safe; no-JS timeline | T03 | Todo | |
| **T06** | Gitea extra_tabs + OBSERVE_PUBLIC_BASE_URL fail-closed links | T04 | Todo | |
| **T07** | Decisions + artifact dispositions | T03 | Todo | |
| **T08** | CT102 CI into observe stream; no terminal regression | T03 | Todo | |

## Hard gates

H1 safe-display before store/stream/UI · H2 auth before public routes · H3 projection identity/sequence · H4 SSE subscribe-first · H5 artifact trust · H6 canonical AgentSession state · H7 fail-open projector · H8 OBSERVE_PUBLIC_BASE_URL fail-closed

## Wave log

| Wave | Date | Handoff | Next | Notes |
|------|------|---------|------|-------|
| 0 | 2026-07-22 | — | T01 | Ledger opened; gap audit vs tip `2471b31` |
