---
id: ADR-0043
title: CT104 HTTPS clone helper is inspected and fail-closed against known write PATs
status: proposed
date: 2026-08-24
owners:
  - platform
scope:
  globs:
    - src/agent_workers/settings.py
    - docker-compose.ct104.yml
    - tests/test_publish_credential_boundary.py
decision_type: security
enforcement: hard
risk_level: high
supersedes: []
superseded_by: []
review_after: 2026-11-24
agent_visibility:
  - review
  - developer
---

# ADR-0043: CT104 HTTPS clone helper is inspected and fail-closed against known write PATs

## Context

ADR-0004 forbids Gitea write tokens on CT104. Workers still need a clone/fetch secret. The HTTPS `credential.helper=store` file was documented as clone-only but not inspected. Env-only `collect_durable_credential_violations()` returned `[]` while `/root/.git-credentials` held `GITEA_BOT_TOKEN`, and `worker-rlm-root` created a durable Gitea branch.

A PAT is opaque: process start cannot prove `read:repository` without a push. Git will offer the stored secret for fetch and push.

## Decision

1. Replace the CT104 deploy HTTPS store with a true `read:repository` PAT. Do not copy `GITEA_BOT_TOKEN`.
2. Inspect the clone helper at worker start. Never log secret values.
3. Fail closed when the store is writable, unreadable after it is known to exist, present without `CT104_FORBIDDEN_GIT_TOKEN_SHA256`, or contains a password whose SHA-256 is on that denylist.
4. Live direct-push of a throwaway non-`main` ref remains the authority for AUTH FAILURE. Env-only PASS is not complete mediation.

## Consequences

- Operators must set `CT104_FORBIDDEN_GIT_TOKEN_SHA256` (hash of known write PATs, never the token) on CT104 when git-credentials is mounted.
- A different write PAT not on the denylist can still pass process start; the live push probe is mandatory after credential changes.
- `_repair_ct104_gitcreds.sh` must not be used: it copies the CT103 write token onto CT104.
