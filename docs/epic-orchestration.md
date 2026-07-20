# Epic orchestration — V4 full build

Boss-agent discipline adapted for the homelab control plane. Use this to finish [gitea_agentic_sdlc_cursor_step_plan_v4.md](../../../gitea_agentic_sdlc_cursor_step_plan_v4.md) **one slice at a time**, with **mandatory deployment verification before the next slice starts**.

This is an **operator / Cursor playbook**, not a new CT104 worker type. Authority stays on CT103 (policy, ledger, publish-broker), CT104 (execution), CT102 (CI truth).

## Roles (mapped)

| Jarala role | Homelab role | Allowed to |
|-------------|--------------|------------|
| **Boss** | Epic supervisor (Cursor skill `v4-epic-boss` or human) | Read/update ledger; spawn one slice wave; demand handoff; **never** implement or SSH-debug |
| **Coordinator** | Slice coordinator (Cursor skill `v4-slice-coordinator`) | Plan + implement **one** slice; run deploy verify; write handoff; update slice doc |
| **Leaf** | CT104 workers + pytest + Gitea Actions | Execute `/agent …`, CI, sandbox — not Cursor subagent swarms |
| **Proof controller** | CT102 + deploy jobs + `/readyz` smoke | Authoritative pass/fail for the deploy gate |
| **Repair controller** | Slice 6F.2 / `ci-repair` (when in scope) | One leased repair path only |

Do **not** spawn parallel repo-mutating Cursor leaves. Parallelism is for read-only research only.

## Hard rules

1. **One active slice.** No starting ticket N+1 until ticket N has a filled [DEPLOY_VERIFY_TEMPLATE.md](handoff/DEPLOY_VERIFY_TEMPLATE.md) and ledger status `Done`.
2. **Phase ≠ epic done.** Finishing 5.6 is not finishing V4. Continue to the next incomplete ticket whose deps are satisfied.
3. **Context discipline.** Boss keeps only: wave #, next ticket ID, done count, blocker one-liner. No diffs, logs, or proof prose in boss context.
4. **Authority.** No Gitea write tokens on CT104; no unsandboxed Risk 2; model self-review is not an acceptance gate.
5. **Completion mode.** Prefer finishing proof/deploy queues over starting new implementation when a slice is “code done but deploy open.”

## Standard loop

```text
1. Orient     — read docs/handoff/boss-ledger.md only
2. Coordinate — one slice (code + tests + slice doc)
3. Deploy     — merge/deploy CT103+CT104; fill DEPLOY_VERIFY
4. Handoff    — write coordinator-handoff-NNN.md; update ledger ≤5 lines
5. Continue   — next incomplete ticket OR stop on user blocker
```

Stop only when ledger `Epic status: complete` or a **user-blocking** blocker is recorded.

## Where truth lives

| Artifact | Owner | Purpose |
|----------|-------|---------|
| [boss-ledger.md](handoff/boss-ledger.md) | Boss | Epic scope, ticket order, next ID, wave log |
| [HANDOFF_TEMPLATE.md](handoff/HANDOFF_TEMPLATE.md) | Coordinator | Compact continuation for next wave |
| [DEPLOY_VERIFY_TEMPLATE.md](handoff/DEPLOY_VERIFY_TEMPLATE.md) | Coordinator | Gate between slices |
| `docs/slice-*.md` | Coordinator | Slice design + acceptance evidence |
| CT103 event ledger / sessions | Control plane | Machine audit (not boss reading material) |
| CT102 Actions | CI | Deploy + test truth |

## Slice done definition

A ticket may move to `Done` only when **all** are true:

1. Code merged (or tip recorded) with green unit tests.
2. Slice doc updated (status, tip SHA, acceptance).
3. [DEPLOY_VERIFY_TEMPLATE.md](handoff/DEPLOY_VERIFY_TEMPLATE.md) filled for that tip on **both** CT103 and CT104 (when the slice touches workers).
4. Homelab smoke named in the ticket (or explicit N/A with reason).
5. ADR created/updated if the architectural-adr skill requires it.
6. Ledger wave row written; `Next ticket` advanced.

## Cursor entry points

- **“Run the V4 epic” / “continue the epic”** → apply `.cursor/skills/v4-epic-boss`
- **“Implement the next slice” / named slice** → apply `.cursor/skills/v4-slice-coordinator` after boss orients from the ledger

## Related

- [architecture.md](architecture.md)
- [slice-v412-typed-sessions.md](slice-v412-typed-sessions.md) — active V4.1.2 umbrella
- [POLICY_GATES.md](POLICY_GATES.md)
- [AGENT_CARD.md](AGENT_CARD.md)
- Source pattern: repo-root `boss-agent/` (Jarala pack — do not run as CT104 agents)
