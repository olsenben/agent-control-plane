# Slice 6D.2 — CT103 publish brokerage (V4.1.1)

**Status:** Homelab signed off 2026-07-19 (barrier cutover)  
**Date:** 2026-07-18 (code); acceptance 2026-07-19  
**Plan:** V4.1.1 Executor Trust-Boundary Hardening §0.7  
**Prerequisite:** [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md), [slice-5.8-6f2-sandboxed-repair.md](slice-5.8-6f2-sandboxed-repair.md)

## Thesis

```text
CT104 = untrusted immutable patch producer (bundle-inbox READY artifacts)
CT103 publish-broker = sole Gitea mutation authority
  snapshot → validate (plumbing) → claim approval → CI intent → push → PR → consume
```

## Bundle layout

```text
agent-state/bundle-inbox/{run_id}/{fix|repair}/{attempt_id}/{bundle_id}/
  manifest.json   # patch_bundle.v1 (producer evidence only)
  patch.diff
  diff_gate_result.json | repair_result.json
  READY

agent-state/publish-snapshots/{run_id}/{bundle_id}/   # CT103-private
agent-state/publish-results/{run_id}/{bundle_id}/     # authoritative
```

`producer_tree_sha` is integrity-only. Authorization uses trusted approval binding + CT103 gate.

## Status model

| Layer | Values |
|-------|--------|
| Worker | `patch_bundle_ready`, `worker_rejected`, `worker_failed` |
| `publish_state` | `not_requested` → `queued` → `validating` → `rejected` \| `remote_pending` → `succeeded` \| … |
| Repair event | `agent.fix_ci_repair_bundle_ready` (handoff); push is CT103 |

Legacy worker `pr_opened_pending_ci` is ignored unless `producer_protocol=patch-bundle.v1`.

## Services

| Compose service | Queues | Credentials |
|-----------------|--------|-------------|
| `worker-state` | `state`, `results-ingest` | none (no git write) |
| `publish-broker` | `publish` only | `GITEA_BOT_TOKEN` + git credentials |

## Broker sequence

1. Snapshot + validate (`git apply --index`, `write-tree`, `commit-tree`)
2. Claim approval
3. Record publish intent + pending-CI for expected commit SHA
4. Push `refs/heads/agent/*`
5. Open/find PR
6. Consume approval; finalize pending CI; comment

Webhook observe accepts active pending **or** matching publish intent.

## Credential boundary

- CT104 production startup fails if `GITEA_AGENT_TOKEN` or `GITEA_BOT_TOKEN` is set
- Emergency rollback only: `CT104_ALLOW_WRITE_TOKEN_DEBT=1`
- No `agent_workers` import of push/PR/comment mutation helpers (architectural test)

## Homelab cutover (barrier)

**Completed 2026-07-18/19** on `demo-app` (seeded fix+repair broker smoke; CT104 `.env` write tokens stripped).

Operator closeout (PR 0 of [slice-v411-closeout.md](slice-v411-closeout.md)): revoke/rotate Gitea PATs that ever lived on CT104; scrub bak/backups/systemd/profiles/remnants; recreate CT104 containers.

## Acceptance

CT104 can propose immutable patch bundles but cannot mutate Gitea. CT103 resolves authorization from trusted state, snapshots and independently validates the bundle, constructs a deterministic commit without executing repository code, records CI intent before push, and performs idempotent remote publication. Plan/review/inspect/explain (and failed-fix) issue comments are posted by CT103 results-ingest using `GITEA_BOT_TOKEN`.

## Related

- [secrets-boundaries.md](secrets-boundaries.md)
- [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md)
- ADR: CT103-only Gitea write (see `docs/adr/`)
