# ADR summary

Index of architecture decisions. Full records live in this directory.

| ID | Title | Status | Date | Decision (one line) |
|----|-------|--------|------|---------------------|
| ADR-0001 | CT102 CI aggregate truth before fix memory | proposed | 2026-07-14 | Webhook signals + Actions API confirm; memory only when aggregate verdict=`verified` |
| ADR-0002 | Anthropic SRT as initial OS sandbox backend | proposed | 2026-07-14 | SRT via SandboxBackend; attestation + fallback deny; CT104 spike gates fix/repair |
| ADR-0003 | Cap-bounded bwrap for SRT inside CT104 Docker | proposed | 2026-07-18 | SYS_ADMIN+NET_ADMIN + seccomp/apparmor unconfined on SRT workers; shared runtime mounts; fail closed on bwrap launch |
| ADR-0004 | CT103-only Gitea write (publish brokerage) | accepted | 2026-07-18 | CT104 patch bundles only; CT103 publish-broker sole mutation authority |
| ADR-0005 | Protected-default-branch policy_source_sha pin | proposed | 2026-07-19 | CT103 resolves immutable policy identity; workers fail-closed detached checkout |
| ADR-0006 | tool_policy.v2 narrowing-only command allowance | proposed | 2026-07-19 | Empty allowance on missing/invalid tools.yaml; effective-policy hash gates repair |
| ADR-0007 | Dual sandbox and execution attestations | proposed | 2026-07-19 | Durable preflight + post-teardown attestations; publish deny if quarantined/missing |
| ADR-0008 | CT102 scheduling and credential-domain split | proposed | 2026-07-19 | Named ops boundary on shared act_runner; not strong principal isolation |
| ADR-0009 | Central repair allowlist and bounded ACP lint class | proposed | 2026-07-19 | Empty allowlist denies; lint_failure default; publish flag staged |

## Review log

- 2026-07-14 `00234bb` — ADR-0001 proposed for slice 6E CI truth loop
- 2026-07-14 — 6E homelab sign-off (PR #20 / `run-cf4c2b2e…`): verdict=`verified`, memory `ci_verified`; ADR-0001 remains `proposed` pending human accept
- 2026-07-14 — ADR-0002 proposed: SRT as initial sandbox backend; Slice 5.6a CT104 spike before `/agent fix`
- 2026-07-14 — Slice 6F.1 evidence + SandboxBackend scaffolding; 6F.2 gated; 5.2 WIP parked in stash `wip-5.2-harden-parked`
- 2026-07-16 — 6F.1 homelab sign-off (PR #20 @ `9b3d83be…`, runs 463/464): `verdict=failing`, evidence `collected`, ledger events×2; repair still off; follow-ups: comment upsert, control-plane agent-runs mount, classifier
- 2026-07-17 — 5.6a signed off: **2d** live env pin CT103+CT104 (`srt` / `5de9f107…`); no new ADR (ADR-0002 still covers SRT backend)
- 2026-07-17 — 6F.2 gate demo on `demo-app` @ `4ebaab0…`: `repair_requested` + `repair_blocked`; worker push deferred to 5.8; no new ADR
- 2026-07-17 `6c40869` / `c3e5d59` — no ADR: 5.8 command_runner + 6F.2 reservation/lease implement ADR-0002 follow-up; push publish wiring still open
- 2026-07-18 `d3d3ea2` — ADR-0003 proposed: CT104 Docker-on-LXC needs bounded caps for bwrap; 5.8+6F.2 demo acceptance on `demo-app` PR #5 @ `16886456…` (`repair_pushed`, CI green, pending re-pointed)
- 2026-07-18 — ADR-0004 accepted: V4.1.1 CT103 publish brokerage; retire CT104 Gitea write tokens; see `slice-6d2-ct103-publish-brokerage.md`
- 2026-07-19 `e7d9f2b` — no new ADR: 6D.2 PR0 closeout (ingest comments + CT104 PAT revoke/scrub); boundary already ADR-0004; umbrella [slice-v411-closeout.md](../slice-v411-closeout.md)
- 2026-07-19 — ADR-0005 proposed: `policy_source_sha` pin + fail-closed policy workspace (V4.1.1 PR1)
- 2026-07-19 — ADR-0006 proposed: `tool_policy.v2` fail-closed empty allowance + effective command-policy hash (V4.1.1 PR2)
- 2026-07-19 — ADR-0007 proposed: dual sandbox/execution attestations + durable bundle-before-teardown (V4.1.1 PR3)
- 2026-07-19 — ADR-0008 proposed: CT102 scheduling/credential-domain split (ops unit)
- 2026-07-19 — ADR-0009 proposed: repair allowlist + bounded ACP lint class (V4.1.1 PR4)
