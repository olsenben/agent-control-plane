# Memory schema (`memory_record.v1`)

Canonical schema for CT103 trajectory memory. Operational guide: [memory.md](memory.md).

## Design principles

1. **Trajectory-centric** — states, actions, observations over time (AMA-Bench alignment), not chat transcripts.
2. **Selective writeback** — store high-signal fields only; do not dump full prompts or raw model streams by default.
3. **Uncertainty first-class** — confidence, staleness, rejected hypotheses.
4. **Three layers** — memory remembers what happened; graph knows what depends on what; CI proves what is broken.

## Record schema

```yaml
schema_version: memory_record.v1
run_id: string
command_kind: inspect|explain|review|plan|fix
created_at: ISO8601

# Scope
issue_id: int | null
pr_id: int | null
repo: owner/name
branch: string
commit_sha: string

# Context inspected
files_inspected: [string]
files_touched: [string]              # empty for read-only runs
adr_ids_applied: [string]

# Graph context (Review MVP+)
blast_radius:
  affected_repos: [string]
  affected_services: [string]
  affected_tests: [string]
  related_adrs: [string]
  missing_graph_edges: [string]      # honest gaps in graph coverage
  confidence: low|medium|high

# Findings (structured — hypotheses until CI verifies)
findings:
  - id: string                       # e.g. F-001
    severity: info|warn|error
    summary: string
    file: string | null
    line_range: [int, int] | null
    confidence: float                # 0.0–1.0
    risk_tags: [string]              # see THREAT_MODEL.md

# Trajectory
failing_tests: [string]
suspected_root_cause: string | null
rejected_hypotheses: [string]
uncertain_hypotheses: [string]
unresolved_questions: [string]
uncertainty_notes: string | null
staleness: fresh|aging|stale

# Governance
risk_class: 0|1|2|3
policy_decision: allow|deny|pending_approval

# Next action
recommended_next_step:
  command: review|plan|fix|human
  rationale: string
  machine_readable: object

# Audit (selective — not full prompt dump)
audit:
  prompt_hash: string                # SHA256 of final prompt
  context_sources: [string]          # e.g. adr_compiler, graph_blast_radius, memory_retrieval
  model_tier: string
  engine: string
  ingested_at: ISO8601
```

## Selective writeback rules

| Store | Do not store by default |
|-------|-------------------------|
| Structured findings + confidence | Full raw prompt text |
| Files inspected, blast-radius summary | Entire cloned repo |
| Rejected/uncertain hypotheses | Every intermediate model token |
| risk_tags, policy_decision | Secrets or credentials |
| prompt_hash (for audit linkage) | Unredacted env values |
| session_id, epistemic_status, evidence_refs (5.7) | Transcripts / full verification logs |

**Slice 5.7:** Typed review/plan memory is admitted only after `session_finished` with a verification claim on the session. Fix memory remains 6E.2 (`ci_verified`). See [slice-5.7-selective-writeback.md](slice-5.7-selective-writeback.md).

Full prompt, retrieved context, model output, and final comment are logged in **run artifacts** (`session_events.jsonl`, run dir) — linked by `run_id`, not duplicated in memory DB.

## Retrieval queries

```text
get_latest_memory(repo, issue_id)
get_memory_trajectory(repo, issue_id, limit)
get_rejected_hypotheses(repo, issue_id)
get_files_with_prior_findings(repo, paths)
get_blast_radius_history(repo, service_name)
search_memory_fts(query, repo?)
memory_as_governance_check(repo, file_paths)   # later: bad attempt history
```

## Write path

```text
result ingest -> validate structured output -> attach risk_tags
  -> append projection event (with risk_tags) to agent-state
  -> upsert memory_record.v1 (selective fields)
  -> optional: enqueue 2070 compression -> memory delta
```

## Read path

```text
dispatch -> memory retrieval + graph blast-radius query
  -> context pack compiler (bounded capsule)
  -> inject into RLMJob; fail closed if over budget
```

## Review MVP memory acceptance

1. Full `memory_record.v1` written on review ingest (not plain text blob).
2. Includes `risk_tags`, `blast_radius` (when graph available), rejected/uncertain hypotheses when applicable.
3. Second command on same issue retrieves prior record.
4. Writeback is selective — no full prompt in SQLite.
