# V4.1.1 Closeout Bundle (umbrella)

**Status:** In progress — PR 0 first  
**Date:** 2026-07-19  
**Plan:** V4.1.1 Executor Trust-Boundary Hardening §0.7  
**Landing rule:** Independently reviewable PRs/ops units — **not** one mega-PR.  
**Excluded:** Explain smoke (already `[done]` in V4).

## Thesis

Finish remaining executor trust-boundary work after 6D.2 publish brokerage: policy provenance, dual attestation lifecycle, CT102 scheduling/credential-domain split (shared-host residual risk explicit), and staged ACP one-class repair enablement.

## Locked decisions

- CT102 remains one CT: **scheduling and credential-domain split** with acknowledged shared-host / shared-Docker residual risk. Not a strong principal boundary unless negative authorization tests prove it.
- First non-demo target: `ai-sdlc-lab/agent-control-plane`, **one named lint/format failure class** only — not general model-authored repair.
- Missing/invalid `tools.yaml` → **empty repository allowance** (no repo command execution).

## Units

| Unit | Scope |
|------|--------|
| **PR 0** | 6D.2 comments + docs; CT104 PAT revoke; full credential scrub; cleanliness gate |
| **PR 1** | `policy_source_*` pin; detached RO policy checkout; remote identity verify |
| **PR 2** | `tool_policy.v2` (fail-closed missing); migrations; effective-policy hash |
| **PR 3** | `sandbox_attestation.v1` + `execution_attestation.v1`; durable bundle before teardown |
| **Ops + ADR** | CT102 scheduling/credential-domain split; negative PR/deploy tests |
| **PR 4** | Centralized allowlist + bounded lint/format class (default disabled) |
| **Ops enable** | Observe-only → repair-no-publish → one-class CT103 publish on ACP |

## Dependency order

```text
PR0 → PR1 → PR2 → PR3 → PR4 → observe → repair-no-publish → narrow publish
                Ops+ADR CT102 ↗
```

## PR 0 acceptance (hard cleanliness gate)

- [x] Pushed from clean checkout; tests green (`e7d9f2b`)
- [x] Both revoked CT104 PATs return unauthorized when exercised (`c918ffc7910d`, `408683dda627` → 401)
- [x] No write token in Compose / containers / env / bak / systemd / profiles / remnants
- [x] CT104-originated Gitea write attempt fails (no token in workers; revoked PATs 401)
- [x] CT103 `agent-bot` (`9d2b2977e2e5`) retained; publish-broker still authenticates
- [ ] Full demo 6D + 6F.2 regression through brokerage (smoke: broker API OK; full E2E optional follow-up)
- [x] Working tree clean for PR 0 commit (local ops scripts remain untracked)

**PR 0 signed off (ops):** 2026-07-19 — CT104 scrub + Gitea DB delete of named `GITEA_AGENT_TOKEN` / `GITEA_BOT_TOKEN` rows; quarantine shredded.

## Related

- [slice-6d2-ct103-publish-brokerage.md](slice-6d2-ct103-publish-brokerage.md)
- [adr/0004-ct103-publish-brokerage.md](adr/0004-ct103-publish-brokerage.md)
- [architecture.md](architecture.md)
- Cursor plan: `v4.1.1_closeout_bundle_*.plan.md`
