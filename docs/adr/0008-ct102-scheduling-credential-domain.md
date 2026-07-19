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
- Separate Linux users, registration tokens, and Docker daemons for CI vs deploy
  are **deferred** (ops follow-up).

### Acceptance tests (document / ops)

1. Normal PR CI runs only on `docker-ci`.
2. Test PR that explicitly requests `deploy` is rejected, withheld, or
   unschedulable — **if this fails, Phase 3 remains operational separation only**.
3. Deploy runs only from protected deployment workflows + protected ref.
4. CI runner identity cannot read deploy runner config, workdir, SSH key, or env
   (requires separate users — pending).
5. CI job env contains no deploy key/token material.
6. Deploy job still works after configs are fully separated.

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
