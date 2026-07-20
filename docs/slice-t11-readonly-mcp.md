# Slice T11 — Read-only MCP graph/memory

**Status:** Implemented — awaiting deploy-verify owner merge  
**Date:** 2026-07-20  
**Epic ticket:** T11  
**Plan:** V4 Phase 24 / impl order item 10  
**Builds on:** Orbit graph (T05), memory projections, verification_state  
**Lane:** `epic/lane-t11-mcp`

## Goal

Expose bounded graph/memory/state queries as a **read-only** MCP server. Static generated projections remain the source of truth. No write, shell, git push, ADR mutation, or state mutation tools.

## Acceptance (ledger smoke)

| Check | Expected |
|-------|----------|
| Tool surface | Allowlisted read tools only; forbidden write names denied |
| Schema | Every result is `mcp_tool_result.v1` and jsonschema-validated |
| Bounds | Lists/strings/payloads truncated to fixed caps |
| Logging | Tool calls logged (stderr + optional JSONL `--log-path`) |
| Source | Reads state projections / graph / memory — not raw untrusted comments |
| Inspector | `docs/mcp.md` documents MCP Inspector against `agentctl mcp serve` |

## Tools

Phase 24 state tools:

- `get_context_capsule`
- `get_relevant_adr_facts`
- `get_finding`
- `get_verification_state`
- `get_policy`
- `get_run_trajectory`

Graph tools:

- `find_callers`
- `find_affected_tests`
- `find_dependency_path`
- `explain_blast_radius`
- `get_context_pack` (local/offline pack — no network)

## Artifacts

| Artifact | Path |
|----------|------|
| Package | `src/agent_control/mcp/` |
| CLI | `agentctl mcp serve\|list-tools\|call` |
| Docs | `docs/mcp.md` |
| Tests | `tests/test_mcp_readonly_t11.py` |

## Forbidden (hard)

```text
update_state, mark_finding_fixed, push_commit, modify_adr, run_shell,
terraform_apply, write_file, shell, exec, sql, publish, approve,
write_repo, write_state, git_push, adr_mutate
```

## Tests

```bash
.venv/bin/pytest tests/test_mcp_readonly_t11.py -q
.venv/bin/ruff check .
```

## Deploy verification

Held for deploy-verify owner (prefer after T08 tip green). Lane stops at `ticket_ready_for_merge`.
