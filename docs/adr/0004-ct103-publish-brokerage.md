# ADR-0004: CT103-only Gitea write (publish brokerage)

- **Status:** Accepted
- **Date:** 2026-07-18
- **Deciders:** Homelab / agent-control-plane
- **Related:** V4.1.1 §0.7, Slice 6D.2, ADR-0003

## Context

After Slice 6D / 6F.2 demo, CT104 held transitional `GITEA_BOT_TOKEN` and `GITEA_AGENT_TOKEN` and performed branch push, PR open, and issue comments. A compromised executor or malicious task branch could therefore mutate Gitea directly. V4.1.1 requires CT104 to return patch evidence only.

## Decision

1. CT104 writes immutable, attempt-scoped, content-addressed bundles under `agent-state/bundle-inbox/` and never holds Gitea write tokens.
2. CT103 `publish-broker` (dedicated Compose service, `publish` queue only) snapshots bundles, independently validates them, constructs commits via plumbing (`apply --index` / `write-tree` / `commit-tree`), records CI intent before push, and performs idempotent push/PR/comment.
3. `results-ingest` remains uncredentialed and only CAS-enqueues by `bundle_id`.
4. Authorization is resolved exclusively from CT103 approval/pending state — never from worker-supplied repo URL, branch, or allowlist.

## Consequences

- Homelab cutover requires a barrier (drain → deploy → strip tokens → rotate → enable brokerage).
- Existing tests that assumed CT104 `publish_fix_branch_and_pr` must target `agent_control.publish`.
- Repair uses non-force FF only; stale heads become terminal, never rebase/force.
