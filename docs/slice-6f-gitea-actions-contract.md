# Slice 6F — Gitea Actions jobs/logs API contract

**Status:** contract harness ready (live fill-in on CT103 against Gitea 1.26)  
**Date:** 2026-07-14  
**Related:** [slice-6f-ci-failure-repair.md](slice-6f-ci-failure-repair.md)

## Routes under test

```text
GET /api/v1/repos/{owner}/{repo}/actions/runs/{run}/jobs
GET /api/v1/repos/{owner}/{repo}/actions/jobs/{job_id}/logs
```

Identifiers:

| Field | Use |
|-------|-----|
| `workflow_run_id` | API run `id` — primary lookup key |
| `run_number` | Display / secondary; **never** used interchangeably with run id |
| `job_id` | Numeric (or stringified) database job id from jobs list |

## Expected fail-closed statuses

| Condition | Evidence status |
|-----------|-----------------|
| 403 | `unavailable` (token capability) |
| 404 | `unavailable` (unsupported route or stale id) |
| 429 | retry with Retry-After; then `unavailable` |
| 5xx / timeout | `unavailable` |
| 200 + empty `jobs` on terminal failed run | `contract_mismatch` |
| Oversized / unexpected content-type / invalid UTF-8 | bounded retain or `unavailable` |

Do **not** scrape UI HTML as a fallback.

## Live probe

```bash
# From CT103 with FIX_CI observe token configured:
.venv/bin/python -m agent_control.ci.gitea_contract_probe \
  --owner ai-sdlc-lab --repo agent-control-plane --run-id <workflow_run_id>
```

Records result under `docs/homelab/` or stdout JSON: `{route, http_status, jobs_count, logs_content_type, notes}`.

## Known upstream risks (shape fail-closed code)

- Empty `jobs[]` for completed runs while UI shows jobs (reported on older Gitea) → `contract_mismatch`
- Job logs may be combined multi-step streams → retain as-is; do not invent failed-step slices

## Homelab fill-in

| Checked at | Gitea version | Run id | Jobs count | Logs OK | Notes |
|------------|---------------|--------|------------|---------|-------|
| (pending live) | 1.26.x | | | | Run probe after deploy of 6F.1 client |
