# Run artifacts

Path: `/mnt/agent-runs/{owner}/{repo}/runs/{run_id}/`

## Inspect MVP required files

- `input_job.json`, `bootstrap.json`, `system_context.json`, `capabilities.json`
- `metadata.json`, `policy_source.json`, `effective_policy.json`
- `context_receipt.json`, `session_events.jsonl`, `rlm_trace.jsonl`
- `redaction_report.json`, `result.json`, `final_report.md`

## Session events

Primary log: `session_events.jsonl` — one JSON object per line with `event`, `request_id`, optional `tool`.

## Result intake

`worker-report` writes:

1. `{run_dir}/events/agent_run_completed.json`
2. `/mnt/agent-state/inbox/ct104-results/{run_id}.json`

Ingest: `agentctl results ingest --inbox`

## Errors

Failed runs write `error.json` and `result.json` with `status=failed`.
