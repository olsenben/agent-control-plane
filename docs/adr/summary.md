# ADR summary

Index of architecture decisions. Full records live in this directory.

| ID | Title | Status | Date | Decision (one line) |
|----|-------|--------|------|---------------------|
| ADR-0001 | CT102 CI aggregate truth before fix memory | proposed | 2026-07-14 | Webhook signals + Actions API confirm; memory only when aggregate verdict=`verified` |
| ADR-0002 | Anthropic SRT as initial OS sandbox backend | proposed | 2026-07-14 | SRT via SandboxBackend; attestation + fallback deny; CT104 spike gates fix/repair |

## Review log

- 2026-07-14 `00234bb` — ADR-0001 proposed for slice 6E CI truth loop
- 2026-07-14 — 6E homelab sign-off (PR #20 / `run-cf4c2b2e…`): verdict=`verified`, memory `ci_verified`; ADR-0001 remains `proposed` pending human accept
- 2026-07-14 — ADR-0002 proposed: SRT as initial sandbox backend; Slice 5.6a CT104 spike before `/agent fix`
- 2026-07-14 — Slice 6F.1 evidence + SandboxBackend scaffolding; 6F.2 gated; 5.2 WIP parked in stash `wip-5.2-harden-parked`
- 2026-07-16 — 6F.1 homelab sign-off (PR #20 @ `9b3d83be…`, runs 463/464): `verdict=failing`, evidence `collected`, ledger events×2; repair still off; follow-ups: comment upsert, control-plane agent-runs mount, classifier
- 2026-07-17 — 5.6a signed off: **2d** live env pin CT103+CT104 (`srt` / `5de9f107…`); no new ADR (ADR-0002 still covers SRT backend)
- 2026-07-17 — 6F.2 gate demo on `demo-app` @ `4ebaab0…`: `repair_requested` + `repair_blocked`; worker push deferred to 5.8; no new ADR
- 2026-07-17 `6c40869` / `c3e5d59` — no ADR: 5.8 command_runner + 6F.2 reservation/lease implement ADR-0002 follow-up; push publish wiring still open
