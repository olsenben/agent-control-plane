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
| **PR 0** | 6D.2 comments + docs; CT104 PAT revoke; full credential scrub; cleanliness gate — **done** |
| **PR 1** | `policy_source_*` pin; detached RO policy checkout; remote identity verify — **done** |
| **PR 2** | `tool_policy.v2` (fail-closed missing); migrations; effective-policy hash — **done** |
| **PR 3** | `sandbox_attestation.v1` + `execution_attestation.v1`; durable bundle before teardown — **done** |
| **Ops + ADR** | CT102 scheduling/credential-domain split; negative PR/deploy tests — **done (docs/ADR)** |
| **PR 4** | Centralized allowlist + bounded lint/format class (default disabled) — **done** |
| **Ops enable** | Observe-only → repair-no-publish → one-class CT103 publish on ACP — **stage 1–2 done; stage 3 open** |

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

## PR 1 acceptance

- [x] Job carries `policy_source_repo|remote|ref|sha|schema_version` from CT103 resolve
- [x] Retry reuses existing pin (`resolve_policy_source_pin(existing=…)`)
- [x] Worker detached checkout; `HEAD == policy_source_sha`; remote identity verified
- [x] Task-branch policy fallback removed (clone failure does not load task tree as policy)
- [x] Repair reservation records pin; CT104 prepares sibling RO policy workspace
- [x] Unit tests: pin resolve, HEAD/remote mismatch, detached checkout, runner fail-closed

**PR 1 signed off (code):** 2026-07-19 — tests green (`test_policy_source_pin` + fake-run / repair suite).

## PR 2 acceptance

- [x] Load `tools.yaml` only from pinned policy workspace (or Gitea raw @ `policy_source_sha` on CT103)
- [x] Missing / invalid / unsupported / unreadable → empty `allowed_command_ids` (deny execution)
- [x] Reject repo argv/executable/shell/env/cwd/network-enable/new IDs/unknown keys
- [x] Narrowing only: `allowed_command_ids` + constraints (timeout ≤ central; path globs validated)
- [x] Record `command_registry_hash` + `effective_command_policy_hash` (sha256 canonical JSON)
- [x] `repair_allowed` / verify gate match effective hash; empty allowance blocks repair
- [x] Migrate `demo-app` + `agent-template` `tools.yaml` to `tool_policy.v2`
- [x] Homelab: push demo-app policy migration; CT103/CT104 tip green

**PR 2 signed off (code+ops):** 2026-07-19 — `34c9619`; demo-app `tools.yaml` @ `c9d3bdc`; `LIVE_TOOL_POLICY_OK` on CT103.

## PR 3 acceptance

- [x] Pre-exec `sandbox_attestation.v1` before fix/repair work (nonce, policy pin, hashes, scrub, ready)
- [x] Post-teardown `execution_attestation.v1` bound to preflight + bundle digest
- [x] Durable READY bundle (with preflight) before workspace destroy
- [x] CT103 publish deny on quarantined / missing / invalid attestations
- [x] Clone hygiene (hooksPath, askpass, credential.helper, GIT_CONFIG_NOSYSTEM, token remotes)
- [x] ADR-0007 proposed; tests green; CT103/CT104 tip deployed

**PR 3 signed off (code+ops):** 2026-07-19 — `aafd962`; Actions 533–535 success; `LIVE_ATTEST_IMPORT_OK` / `CT104_ATTEST_OK`.

## Ops + ADR — CT102 scheduling/credential-domain split

- [x] ADR-0008 proposed: named boundary, residual shared-host/Docker risk, acceptance tests, physical-separation trigger
- [x] Update `runners.md`, `deploy.md`, `cicd-setup.md` (no strong-isolation claim)
- [ ] Ops follow-up: separate CI/deploy Linux users + negative PR→deploy scheduling test on live CT102

## PR 4 acceptance

- [x] Central `decide_repair_repository` (allowed, reason_code, normalized repo, match, class, policy hash)
- [x] `FIX_CI_REPAIR_ALLOWED_REPOS` empty = deny; no wildcards; invalid fails startup
- [x] Default class `lint_failure`; path envelope prohibits trust-boundary paths
- [x] Demo intentional-fail heuristic hard-gated to `demo-app` only
- [x] `FIX_CI_REPAIR_PUBLISH_ENABLED` default false (broker gate)
- [x] Homelab tip green + closeout sign-off

**PR 4 signed off (code+ops):** 2026-07-19 — `38fc591`; Actions 539–541 success; `LIVE_REPAIR_POLICY_OK` (allowlist empty denies despite live `FIX_CI_REPAIR_ENABLED=true`).

## Ops enablement (staged)

**Host knobs (CT103):** `FIX_CI_REPAIR_ALLOWED_REPOS=ai-sdlc-lab/agent-control-plane`, `FIX_CI_REPAIR_ALLOWED_CLASSES=lint_failure` (default), `FIX_CI_REPAIR_PUBLISH_ENABLED=false`; observe/evidence/repair enabled; worker-state recreated.

| Stage | Result |
|-------|--------|
| Config live | Pass — allowlist ACP only; repair publish off; remote publish remains on for fix brokerage |
| ACP lint class allow | Pass — `STAGE2_REPO_LINT_OK` |
| Non-lint / demo deny | Pass — `test_failure` + `demo-app` denied |
| Publish deny | Pass — `repair_publish_disabled` at decide + broker policy |
| Repair gate (synthetic strong sandbox) | Pass — `STAGE2_REPAIR_GATE_OK` |
| Bundle + dual attest; publish still denied | Pass — `STAGE2_BUNDLE_ATTEST_OK` / `STAGE2_BROKER_POLICY_DENY_OK` |
| CT102 deploy not on PR | Pass — `deploy*.yaml` no `pull_request`; `ci.yaml` is `docker-ci` only (ops separation; ADR-0008) |
| ACP `tools.yaml` @ tip | Pass — added `.agent/policies/tools.yaml` v2 (`ruff_check` only) @ `3c11499`; `ACP_TOOLS_OK` |

**Not yet (stage 3):** `FIX_CI_REPAIR_PUBLISH_ENABLED=true` + real ACP lint failure → CT103 brokerage publish.

**Signed ops stage 1–2:** 2026-07-19 — policy gates + bundle/attest + publish deny + CT102 workflow PR check; ACP tools pin green.

## Related

- [slice-6d2-ct103-publish-brokerage.md](slice-6d2-ct103-publish-brokerage.md)
- [adr/0004-ct103-publish-brokerage.md](adr/0004-ct103-publish-brokerage.md)
- [adr/0007-dual-attestation-lifecycle.md](adr/0007-dual-attestation-lifecycle.md)
- [adr/0008-ct102-scheduling-credential-domain.md](adr/0008-ct102-scheduling-credential-domain.md)
- [adr/0009-repair-allowlist-bounded-class.md](adr/0009-repair-allowlist-bounded-class.md)
- [architecture.md](architecture.md)
- Cursor plan: `v4.1.1_closeout_bundle_*.plan.md`
