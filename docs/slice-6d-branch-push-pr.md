# Slice 6D — Branch Push + PR

**Status:** implemented (homelab fake sign-off 2026-07-13, issue #19 → PR #20)

After Slice 6C closed-world diff gate passes, CT104 may publish an approved patch to a deterministic `agent/{run_id}` branch and open a structured Gitea PR. **Nothing is verified until Slice 6E (CT102 CI).**

**Prerequisite:** [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md), [slice-5.1-engine-reliability.md](slice-5.1-engine-reliability.md), [slice-4c-result-ingest-automation.md](slice-4c-result-ingest-automation.md), [slice-6d1-hollow-artifact-guardrails.md](slice-6d1-hollow-artifact-guardrails.md)

**Progression:** 6A approval → 6B local patch → 6C diff gate → **6D push/PR** → 6E CT102 CI

## Scope boundary

| Layer | 6C | **6D** | 6E |
|-------|-----|--------|-----|
| Gate | Post-apply closed-world | Full 6C re-run before commit | — |
| Base SHA | — | `approved_base_ref` + `approved_base_sha` binding + stale checks | — |
| Remote writes | None | `agent/{run_id}` + PR | Observe CT102 |
| Status | `local_patch_passed` | `pr_opened_pending_ci` | `ci_verified` |

## Feature flag

- `FIX_REMOTE_PUBLISH_ENABLED=false` (default) — 6C-only behavior
- When `true`: `JobSafety.allow_push=True`, `allow_network=True`
- Only `FIX_REMOTE_PUBLISH_ENABLED` controls whether publish runs (no alternate env names)

## Approval lifecycle (6D)

```text
human.approval_granted     # captures approved_base_ref + approved_base_sha
  → agent.fix_enqueued     # approval reserved (not consumed)
  → agent.run_completed
  → agent.approval_consumed   # only after ingest sees fix_status=pr_opened_pending_ci
```

Partial push (branch OK, PR failed or stale base after push): reservation **held** — `branch_published_pr_failed`.

## Stale-base policy (strict)

| Checkpoint | Rule |
|------------|------|
| At approval | `approved_base_sha` = current `approved_base_ref` tip (default branch) |
| Before publish commit | workspace `HEAD` must **equal** `approved_base_sha` |
| Before push | remote `approved_base_ref` tip must **equal** `approved_base_sha` |
| Before PR open | remote `approved_base_ref` tip must **equal** `approved_base_sha` |

If the default branch advances after the agent branch was pushed but before PR open: record `branch_published_pr_failed` with `stage=stale_approval_base`, keep reservation held, require `resume-pr` / rebase / operator action.

## Push vs PR base (no ambiguity)

| Operation | Rule |
|-----------|------|
| Push destination | Must be `refs/heads/agent/*` only |
| Push destination | Must **not** be `main`, `master`, default, or any protected/base branch |
| PR base | Must equal configured `primary_branch` / default branch (`approved_base_ref`) |
| Direct push to PR base | **Forbidden** |

## Flow

```text
diff_gate_passed
  → evaluate_patch_artifact (6D.1 — blocks empty patch)
  → run_publish_preflight (6D.1 — identity, diff --check)
  → verify workspace HEAD == approved_base_sha
  → re-run run_closed_world_diff_gate
  → git checkout -B agent/{run_id}
  → verify workspace HEAD == approved_base_sha (again)
  → git add -A -- {allowed paths}
  → git commit (provenance trailers)
  → verify remote approved_base_ref tip == approved_base_sha
  → git push origin HEAD:refs/heads/agent/{run_id}
  → verify remote approved_base_ref tip == approved_base_sha (again)
  → Gitea create_pull_request (base = primary_branch)
  → remote_publish_result.json (redacted)
  → report + inbox ingest
```

## Artifacts

| Artifact | When |
|----------|------|
| `remote_publish_result.json` | Publish attempted (secrets redacted) |
| `remote_publish_plan.json` | `dry_run=True` only (secrets redacted) |
| `error.json` | `stage`: `stale_approval_base`, `branch_push`, `pr_open` (secrets redacted) |

## Status vocabulary

| Field | Value | Meaning |
|-------|-------|---------|
| `fix_status` | `local_patch_passed` | Gate pass; publish disabled **or** dry-run passed |
| `publish_state` | `dry_run_passed` | Dry-run only — not a real publish lifecycle |
| `status` | `completed` | Dry-run and successful local patch |
| `terminal_status` | `completed` | Dry-run and successful local patch |
| `fix_status` | `publish_failed` | Pre-push failure; reservation released |
| `fix_status` | `branch_published_pr_failed` | Push OK; PR or post-push stale base; reservation held |
| `fix_status` | `pr_opened_pending_ci` | PR open; **not verified** |

Dry-run contract: never pushes, never opens PR, never sets `pr_opened_pending_ci`.

## Secret redaction gate

Before writing any of: `remote_publish_result.json`, `remote_publish_plan.json`, `error.json`, Gitea comments, session events, worker-report payloads, or publish error messages — run `SecretRedactor` (token URLs, `Authorization` headers, HTTP basic auth, `GITEA_AGENT_TOKEN`, `GITEA_BOT_TOKEN`). See `agent_workers.publish.safe_write`.

## Token policy

| Token | Scope |
|-------|-------|
| `GITEA_BOT_TOKEN` | **CT103 only** — push + PR + comments (V4.1.1 / 6D.2) |

CT104 no longer publishes. See [slice-6d2-ct103-publish-brokerage.md](slice-6d2-ct103-publish-brokerage.md).

## Implementation order

0. Schema + status enums + event fields
1. Approval reservation + `approved_base_sha` capture
2. Gate/ref/remote-host/staging validation helpers
3. `RemotePublishResult` + dry-run writer
4. Gitea client + `open-pr` CLI
5. CT104 `remote_publish` module
6. Runner/report integration
7. `resume-pr` path
8. Homelab fake E2E

## Tests

| Test | Covers |
|------|--------|
| `test_publish_6d.py` | stale base, commit trailers, dry-run, reservation, ingest consume, staging guards |
| `test_publish_env_var_names.py` | only `FIX_REMOTE_PUBLISH_ENABLED` controls publish |
| `test_pr_base_advanced_after_push_blocks_pr.py` | default branch advances after push → no PR, partial state |
| `test_publish_error_redaction.py` | credentials stripped from artifacts and messages |
| `test_push_destination_not_base_branch.py` | push ref is `refs/heads/agent/*`, never PR base |
| `test_dry_run_status_contract.py` | dry-run status/artifact contract |
| `test_gitea_client_push_pr.py` | mocked PR API |

## Homelab acceptance

Deploy with `FIX_REMOTE_PUBLISH_ENABLED=true` after Milestone 1 (5.1 + 4C) sign-off. Recommended before official-engine 6D runs: [slice-5.2-plan-quality-gate.md](slice-5.2-plan-quality-gate.md) and [slice-5.3-issue-task-backfill.md](slice-5.3-issue-task-backfill.md) (homelab issues #13–#14). Fake engine first; then one official-engine trivial fix on a single allowed file.

**Next (done):** [slice-6e-ct102-ci-truth-loop.md](slice-6e-ct102-ci-truth-loop.md) — CT102 observe/aggregate signed off 2026-07-14. **Then (done 2026-07-16):** [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md) 6F.1 evidence. **Open:** sandbox attestation + 6F.2.

## Related

- [slice-6c-closed-world-diff-gate.md](slice-6c-closed-world-diff-gate.md)
- [slice-6e-ct102-ci-truth-loop.md](slice-6e-ct102-ci-truth-loop.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [deploy.md](deploy.md)
- [secrets-boundaries.md](secrets-boundaries.md)
