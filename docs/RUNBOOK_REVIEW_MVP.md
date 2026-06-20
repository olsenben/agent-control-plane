# Runbook: Review MVP

Verify `/agent review` with snapshot/ADR context, minimal cross-repo graph, selective memory writeback, and second-command retrieval.

Prerequisites: Inspect MVP complete (2026-06-14). See [deploy.md](deploy.md).

## Pre-flight

```bash
# CT103
agentctl readyz
agentctl worker doctor

# Graph snapshot (when implemented — Tree-sitter + catalog-info.yaml)
agentctl graph snapshot

# Blast-radius + context pack for issue
agentctl graph blast-radius --repo ai-sdlc-lab/agent-control-plane \
  --files src/agent_control/workflows/dispatch.py
agentctl graph context-pack --repo ai-sdlc-lab/agent-control-plane --issue 2
```

## Steps

### 1. Trigger review

On a Gitea issue in an allowed repo (e.g. `demo-app`):

```text
/agent review
```

### 2. Verify CT103 path

```bash
agentctl runs list --limit 5
agentctl runs show <run_id>
agentctl runs events <run_id>
```

Expect: webhook event → reducer `dispatch_recommended` → rlm-root enqueued.

### 3. Verify CT104 execution

```bash
agentctl runs logs <run_id>
```

Expect: read-only clone, bounded context packet, model call, structured output, session artifacts.

### 4. Verify Gitea comment

Comment should include:

```markdown
## Agent Review

### Finding
...

### Files inspected
- ...

### Cross-repo / blast-radius context
Potentially affected repos: ...
Potentially affected services: ...
Potentially affected tests: ...
Related ADRs: ...

### Confidence
...

### Recommended next command
/agent plan
```

If graph edges missing, comment should list `missing_graph_edges`.

### 5. Ingest result

```bash
agentctl results ingest --inbox
```

### 6. Verify memory writeback

```bash
# when CLI exists:
agentctl memory show --repo demo-app --issue <issue_id>
```

Expect selective `memory_record.v1` per [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md):

- findings, risk_tags, blast_radius, rejected/uncertain hypotheses
- prompt_hash + context_sources in audit — not full prompt text

### 7. Second command retrieval

On same issue:

```text
/agent plan
```

Verify dispatch context includes prior review memory (check run artifacts: `context_pack.json`, `plan_result.json`). Plan posts a structured comment with scope, steps, CI hints, and blast-radius.

**Plan MVP:** `OfficialRLMEngine` and `FakeRLMEngine` support `/agent plan` with `plan_result.v1`. `/agent fix` remains blocked at dispatch (Risk 2).

### 8. Policy check

Confirm no write-capable job ran without approval:

```bash
agentctl runs list --kind fix
# should be empty unless explicit approval granted
```

## Pass criteria

All items in [EVALS.md](EVALS.md) Review MVP table pass.

Update [AGENT_CARD.md](AGENT_CARD.md) `last_verified.review_mvp` date.

## Rollback

- Set `ENFORCE_PUBLIC_SURFACE_RESTRICTION=1` to block unexpected commands
- Stop CT104 workers: `docker compose --profile workers-ct104 stop`
- Re-run with `MODEL_ROUTING_POLICY=fake` for offline debugging

## Related

- [graph-indexer.md](graph-indexer.md)
- [POLICY_GATES.md](POLICY_GATES.md)
- [architecture.md](architecture.md)
