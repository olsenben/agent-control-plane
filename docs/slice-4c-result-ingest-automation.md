# Slice 4C — Event-Driven Result Ingest / Reconciliation

**Status:** planned  
**Prerequisite:** CT104 `worker-report` inbox writes (live)  
**Blocks:** [6D branch push + PR](#related) — **mandatory before any remote write**

Also referenced as **6A.1** in roadmap discussions (approval/fix handlers depend on accurate ledger).

## Thesis

Manual/cron `agentctl results ingest --inbox` was acceptable for homelab bring-up. It now causes user-visible false negatives: Gitea comment exists, but CT103 ledger lacks the plan run → approve/fix lookup fails.

**Cross-cutting reliability gap B:** event synchronization between CT104 execution and CT103 governance.

## Problem (observed)

```text
CT104 worker-report → inbox/ct104-results/{run_id}.json
CT103 approve/fix   → resolve_plan_for_target reads event ledger only
User action         → "No plan run found" / "No plan matches target WI-xxxx"
```

Interim homelab bridge: 2-minute cron on CT103 ([deploy.md](deploy.md#result-ingest-ct103)). Not in repo; must be verified on host.

## Target design

Event-driven ingest as **primary**; periodic sweep as **safety net**.

```text
CT104 worker-report writes inbox JSON
  → CT104 enqueues results-ingest job into Redis (primary)
  → CT103 ingest worker processes that exact file
  → CT103 appends agent.run_completed | agent.run_failed

Fallback (CT103 ingest-watch service):
  watchfiles on inbox dir (backup over NFS)
  + periodic sweep every N seconds (safety net)
```

**Do not rely on file watching alone over NFS.** Redis notify/enqueue is primary; watch + sweep is backup.

### Plan resolution fallback

When ledger lookup fails, approve/fix handlers may read **pending inbox JSON** for matching `command_kind=plan` before failing. Ledger remains source of truth after merge.

Optional: CT103 internal HTTP hook from `worker-report` after inbox write (same-host NFS, no Tailscale hop).

## Implementation phases

### Phase 1 — Redis-enqueued ingest (primary)

- `worker-report` enqueues `ingest-inbox-file` job with `{run_id, inbox_path}` after write
- CT103 `worker-state` (or dedicated ingest worker) processes one file idempotently
- Idempotency key: `run_id` + inbox file mtime/hash

### Phase 2 — Ingest-watch + sweep (backup)

- CT103 service: `watchfiles` on `inbox/ct104-results/`
- Debounced processing (avoid double-ingest with Phase 1)
- Periodic sweep: `agentctl results ingest --inbox` every 60–120s as last resort

### Phase 3 — Plan resolution fallback

- `resolve_plan_for_target`: if no ledger match, scan pending inbox for plan runs with matching `approval_target_id` / run metadata
- Document ordering: ingest job should beat user action in normal case; fallback covers race

### Phase 4 — Failure path integration

- Ingest `status=failed` inbox events from Slice 5.1 RQ exception handler
- Ledger event type: `agent.run_failed` (or `agent.run_completed` with failed status — pick one, document)

## Acceptance criteria

1. Plan comment posted → ledger has `agent.run_completed` within seconds **without manual ingest**
2. Approve/fix immediately after plan comment succeeds (no cron dependency)
3. Duplicate ingest is idempotent (`created=false` on replay)
4. Sweep catches files missed by Redis enqueue (induced failure test)
5. Failure inbox events from parse/apply/gate appear in ledger

## Out of scope

- Replacing event ledger as source of truth
- CT102 CI result ingest (6E)

## Rollback

- Disable ingest worker; restore manual/cron ingest only
- Plan resolution fallback can remain enabled (read-only safety)

## Related

- [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md) — failure inbox events must be ingested
- [slice-6a-approval-plumbing.md](slice-6a-approval-plumbing.md)
- [slice-6b-local-patch-artifact.md](slice-6b-local-patch-artifact.md) — follow-up section (superseded by this doc)
- [deploy.md](deploy.md#result-ingest-ct103)
