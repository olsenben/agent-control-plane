# Boss ledger — V9 Agent Observatory (approved plan gap-closure)

Epic supervisor state. Prior: [boss-ledger-v8.md](boss-ledger-v8.md) (residual QA; T02+T04 WaitingHuman). Plan: `.cursor/plans/v6_agent_observatory_epic_2ab66432.plan.md` (numbered V9 — homelab V6 already used).

| Field | Value |
|-------|-------|
| **Epic name** | V9 — Agent Observatory (safe-display, projection, OAuth UI, SSE race, panels) |
| **Baseline tip** | `2471b31` |
| **Orchestration** | [epic-orchestration.md](../epic-orchestration.md) |
| **Integration branch** | `main` |
| **Epic status** | complete |
| **Tickets done** | 8 / 8 |
| **Next ticket** | EPIC_COMPLETE |
| **Latest handoff** | [deploy-verify-v9-t07-t08-20260722.md](deploy-verify-v9-t07-t08-20260722.md) |
| **Last boss action** | 2026-07-22 — T07+T08 deploy-verify PASS on CT103+CT104 tip `fba0846`; smoke `V9_T07_SMOKE_OK` + `V9_T08_SMOKE_OK`; V9 epic spine complete |
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
| **T01** | observe_event.v1 + safe-display + producer inventory | — | Done | `c50ed96` |
| **T02** | observe.sqlite idempotent display-safe projection; fail-open async | T01 | Done | `6a67233` |
| **T05** | Gitea OAuth shell + 401/redirect/403/503; mount protected routes | T02 | Done | `1f71bf6` |
| **T03** | Protected SSE subscribe-first + Redis id-notify + Last-Event-ID | T05 | Done | `dae78e3` |
| **T04** | Jinja+HTMX five-panel UI; text-safe; no-JS timeline | T03 | Done | `8fb905d` |
| **T06** | Gitea extra_tabs + OBSERVE_PUBLIC_BASE_URL fail-closed links | T04 | Done | `4a4998a` |
| **T07** | Decisions + artifact dispositions | T03 | Done | `fba0846` |
| **T08** | CT102 CI into observe stream; no terminal regression | T03 | Done | `fba0846` |

## Hard gates

H1 safe-display before store/stream/UI · H2 auth before public routes · H3 projection identity/sequence · H4 SSE subscribe-first · H5 artifact trust · H6 canonical AgentSession state · H7 fail-open projector · H8 OBSERVE_PUBLIC_BASE_URL fail-closed

## Wave log

| Wave | Date | Handoff | Next | Notes |
|------|------|---------|------|-------|
| 0 | 2026-07-22 | — | T01 | Ledger opened; gap audit vs tip `2471b31` |
| 1 | 2026-07-22 | [026](coordinator-handoff-026.md) | T02 | T01 code landed + pushed, tip `4dc32e5`; ruff clean, pytest 685 passed; Deploy gate — CT102 Actions / homelab deploy verification still owed before Done |
| 2 | 2026-07-21 | [deploy-verify-v9-t01-20260721.md](deploy-verify-v9-t01-20260721.md) | T02 | T01 Done; CT103+CT104 tip `c50ed96`; CI #842/#844/#843 noted PASS; `/readyz` redis+state ok; container smoke `V9_T01_SMOKE_OK`; unit 10/10 |
| 3 | 2026-07-22 | [027](coordinator-handoff-027.md) | T02 | T02 code landed + pushed, tip `41bad77`; ruff clean, pytest 711 passed; no new /observe routes; CT102 Actions / homelab deploy verification still owed before Done |
| 4 | 2026-07-21 | [deploy-verify-v9-t02-20260721.md](deploy-verify-v9-t02-20260721.md) | T05 | T02 Done; CT103+CT104 tip `6a67233`; `/readyz` redis+state ok; smoke `V9_T02_SMOKE_OK` (rebuild 102 projected / agentctl observe rebuild) |
| 5 | 2026-07-22 | [028](coordinator-handoff-028.md) | T05 | T05 code landed + pushed, tip `ab2f7ef`; ruff clean, pytest 742 passed; oauth login/callback fail-closed 503 (secrets unset, human step per V8 T04 checklist still owed); CT102 Actions / homelab deploy verification still owed before Done |
| 6 | 2026-07-22 | [deploy-verify-v9-t05-20260722.md](deploy-verify-v9-t05-20260722.md) | T03 | T05 Done; CT103+CT104 tip `1f71bf6`; `/readyz` redis+state ok; smoke `V9_T05_SMOKE_OK` (401 unauth API, 302 unauth HTML, 503 oauth login, 401 unauth SSE) |
| 7 | 2026-07-22 | [029](coordinator-handoff-029.md) | T04 | T03 code landed + pushed, tip `23f8457`; ruff clean, pytest 756 passed; H4 subscribe-first/Redis id-notify/Last-Event-ID shipped; NPM `proxy_buffering` step documented, not live-smoked (no NPM access); CT102 Actions / homelab deploy verification still owed before Done |
| 8 | 2026-07-22 | [deploy-verify-v9-t03-20260722.md](deploy-verify-v9-t03-20260722.md) | T04 | T03 Done; CT103+CT104 tip `dae78e3`; `/readyz` redis+state ok; smoke `V9_T03_SMOKE_OK` (401 unauth SSE, history ids 1–2, live notify id 3, shared token) |
| 9 | 2026-07-22 | [030](coordinator-handoff-030.md) | T06 | T04 code landed + pushed, tip `b914d30`; ruff clean, pytest 773 passed; five-panel Jinja+HTMX UI (current state / decision timeline / decisions placeholder / live logs SSE+HTMX-poll / artifacts placeholder), text-safe (HTML/ANSI/Markdown escape as text, no raw/prohibited payload in page/HTMX/SSE), no-JS timeline pagination; ADR-0031 accepted; CT102 Actions / homelab deploy verification still owed before Done |
| 10 | 2026-07-22 | [deploy-verify-v9-t04-20260722.md](deploy-verify-v9-t04-20260722.md) | T06 | T04 Done; CT103+CT104 tip `8fb905d`; `/readyz` redis+state ok; smoke `V9_T04_SMOKE_OK` (five panels auth shared token, no-JS timeline pagination, unauth HTML 302 redirect) |
| 11 | 2026-07-22 | [031](coordinator-handoff-031.md) | T06 | T06 code landed + pushed, tip `08382e2`; ruff clean, pytest 808 passed; `OBSERVE_PUBLIC_BASE_URL` fail-closed (H8: unset by default, no LAN/HTTP default, https required in secure mode, `run_id` URL-safety check before interpolation); `format_invocation_started`/session comment projection/NL-invocation stub all extend with an Observe link only when configured; `/readyz` reports it informationally, never gates readiness; Gitea `extra_tabs.tmpl` + version-pinned (Gitea `1.26.2`) install/upgrade docs under `docs/gitea-custom/` (CT100 install remains a documented human follow-up, not blocking Deploy gate); CT102 Actions / homelab deploy verification still owed before Done |
| 12 | 2026-07-22 | [deploy-verify-v9-t06-20260722.md](deploy-verify-v9-t06-20260722.md) | T07 ∥ T08 | T06 Done; CT103+CT104 tip `4a4998a`; `/readyz` redis+state ok, `observe_public_base_url=unset`; smoke `V9_T06_SMOKE_OK` (no Observe link/warning path when unset); CT100 `extra_tabs` human follow-up not blocking |
| 13 | 2026-07-22 | [032](coordinator-handoff-032.md) | T07 ∥ T08 (deploy-verify) | T07+T08 code landed + pushed, tip `df1d6d8`; ruff clean, pytest 890 passed (up from 808 at T06 land time); T07: `observe.decisions`/`observe.artifacts` (H5 trust gates, no raw artifact bytes, no chain_of_thought leakage) wired into panels 3+5, two new artifact view/download routes; T08: `observe.ci_channel` teaches the projector `fix_run_id`→`run_id` resolution for `agent.fix_ci_*`, flattens `WorkflowObservation` before H1 classification, adds a `category=ci` tag + CT102 deep link, and reads panel 1's CI phase live from the canonical `verification_claim.json` (no event-replay regression risk); ADR-0032 accepted; CT102 Actions / homelab deploy verification still owed before Done on both tickets |
| 14 | 2026-07-22 | [033](coordinator-handoff-033.md) | T07 ∥ T08 (deploy-verify) | T08 standalone confirmation session found the T07+T08 wave already landed at `df1d6d8`/`5b3f9da`; verified T08's slice matches this session's own work exactly (no further T08 file changes needed); landed a separate previously-uncommitted `V9 T06: deploy-verify closeout` (`d1df0b8`); fixed one pre-existing unrelated ruff issue in an untracked scratch script; tip bumped to `fba0846` (lint-only, no functional change); ruff clean, pytest 890 passed; pushed |
| 15 | 2026-07-22 | [deploy-verify-v9-t07-t08-20260722.md](deploy-verify-v9-t07-t08-20260722.md) | EPIC_COMPLETE | T07+T08 Done; CT103+CT104 tip `fba0846`; CT104 pinned from `4bbf438`; `/readyz` + compose ok; smoke `V9_T07_SMOKE_OK` (decisions panel, metadata_only artifacts, path traversal 404) + `V9_T08_SMOKE_OK` (fix_ci projection, timeline CI marker, terminal no-regress); V9 epic 8/8 complete |
