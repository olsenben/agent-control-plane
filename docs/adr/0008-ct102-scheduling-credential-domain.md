---
id: ADR-0008
title: CT102 scheduling and credential-domain split
status: proposed
date: 2026-07-19
---

# ADR-0008 — CT102 scheduling and credential-domain split

## Context

CT102 hosts Gitea Actions for untrusted PR CI (`docker-ci`) and protected deploy
jobs (`deploy`). Both labels currently register on one `act_runner` container on
the same LXC. V4.1.1 closeout requires naming this boundary honestly before
non-demo ACP repair enablement.

## Decision

Call the boundary **CT102 scheduling and credential-domain split** — **not** a
strong principal boundary.

### What is mitigated

- Workflow scheduling lanes: `ci.yaml` → `docker-ci`; `deploy*.yaml` → `deploy`
  (test jobs still on `docker-ci`).
- Deploy workflows trigger only on protected `main` push / `workflow_dispatch`
  (not on pull_request).
- Deploy secrets (`DEPLOY_*`) are injected only into deploy job env; CI jobs do
  not declare those secrets.
- Runtime `.env` stays on CT103/CT104; never passed through CI.

### What is not mitigated (residual risk)

- Shared host / shared Docker trust surface: compromise of the CT102 Docker
  daemon or `act_runner` process can defeat label-based separation.
- A malicious PR that adds a new workflow with `runs-on: deploy` is **not**
  blocked by labels alone if Gitea schedules that label for the PR event.
  Server-side workflow trust / protected-path controls are required for a
  principal boundary claim.
- Separate Linux users + per-lane act_runner registrations are **done** (2026-07-20):
  `runner-ci` → `ct102-ci` (`docker-ci`); `runner-deploy` → `ct102-deploy` (`deploy`).
- Shared Docker daemon / host trust surface remains (not a principal boundary).
- Separate Docker daemons / CTs remain deferred until physical-separation trigger.

### Acceptance tests (document / ops)

1. Normal PR CI runs only on `docker-ci` — **pass** (`ct102-ci`).
2. Test PR that explicitly requests `deploy` is rejected, withheld, or
   unschedulable — **fail (expected)**: PR #24 / run 567 job `should-not-be-trusted`
   scheduled on `ct102-deploy`. Phase remains **operational separation only**.
3. Deploy runs only from protected deployment workflows + protected ref — **pass**
   for `deploy.yaml` / `deploy-ct104.yaml` triggers (not `pull_request`).
4. CI runner identity cannot read deploy runner `.runner` / data dir —
   **pass** (`CROSS_READ_DENY_OK` between `runner-ci` and `runner-deploy`).
5. Neg-deploy probe job env contained no `DEPLOY_*` vars (`NO_DEPLOY_SECRETS_IN_ENV`);
   note: a PR workflow that *references* `secrets.DEPLOY_*` may still receive them
   on same-repo PRs — Gitea secret ACL / workflow trust required for stronger claims.
6. Deploy lane still registered and healthy after split (`ct102-deploy` declared
   labels `[deploy]`; prior `main` deploys green at tip `96937be`).

### Trigger for physical separation

Move deploy to a separately authorized runner scope or separate CT/VM when:
non-demo production traffic requires principal isolation, or acceptance test (2)
cannot pass on the shared runner.

## Consequences

- Docs (`runners.md`, `deploy.md`, `cicd-setup.md`) must not claim strong
  isolation while one act_runner advertises both labels.
- Staged ACP repair enablement may proceed under this named residual risk.

## Related

- [runners.md](../runners.md), [deploy.md](../deploy.md), [cicd-setup.md](../cicd-setup.md)
- V4.1.1 closeout Ops unit / [slice-v411-closeout.md](../slice-v411-closeout.md)
