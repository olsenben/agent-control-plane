# Read-only MCP server (T11 / Phase 24)

Expose bounded **graph / memory / verification-state** queries over the
[Model Context Protocol](https://modelcontextprotocol.io/). This server is
**read-only**: it never writes repos, state, ADRs, or runs shell.

## Quick start

From the control-plane checkout (venv activated):

```bash
agentctl mcp list-tools
agentctl mcp call get_verification_state --args '{"repo":"ai-sdlc-lab/agent-control-plane"}'
python -m agent_control.mcp
# or
agentctl mcp serve
```

Optional audit log:

```bash
agentctl mcp serve --log-path /tmp/mcp-tool-calls.jsonl
```

## MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

In the Inspector UI, configure a **stdio** server:

| Field | Value |
|-------|--------|
| Command | `python` (or path to venv python) |
| Args | `-m agent_control.mcp` |
| CWD | `…/agent-control-plane` (this repo) |
| Env | Same as control plane (`AGENT_STATE_ROOT`, graph/memory paths, …) |

Alternatively:

| Field | Value |
|-------|--------|
| Command | `agentctl` |
| Args | `mcp serve` |

Then:

1. Connect and confirm `initialize` succeeds (`serverInfo.name` =
   `agent-control-plane-readonly`).
2. **List tools** — only the allowlisted read tools appear (no write/shell).
3. Invoke e.g. `get_policy` with
   `{"repo":"ai-sdlc-lab/agent-control-plane","policy_name":"recursive_context"}`.
4. Confirm the result text is JSON with `"schema":"mcp_tool_result.v1"` and
   `"ok": true|false`.

## Allowlisted tools

| Tool | Purpose |
|------|---------|
| `get_context_capsule` | Capsule from `verification_state` projection |
| `get_relevant_adr_facts` | ADR facts for changed files |
| `get_finding` | One memory finding by id |
| `get_verification_state` | `summaries/verification_state.json` |
| `get_policy` | Allowlisted local YAML (`tools`, `recursive_context`, …) |
| `get_run_trajectory` | Memory + events + recursive trajectory for `run_id` |
| `find_callers` | Import callers for a file |
| `find_affected_tests` | Blast-radius tests |
| `find_dependency_path` | Shortest graph path |
| `explain_blast_radius` | Full blast-radius export |
| `get_context_pack` | Offline pack (graph/ADR/memory; **no network**) |

## Guarantees

- Results are **schema-validated** (`mcp_tool_result.v1`).
- Lists/strings/payloads are **size-bounded**.
- Tool calls are **logged** (stderr; optional JSONL).
- Reads use **state projections / graph DB / memory DB**, not raw issue comments
  as authority.
- Forbidden names (`update_state`, `run_shell`, `push_commit`, `modify_adr`, …)
  are rejected even if requested.

## Protocol note

The stdio transport speaks **newline-delimited JSON-RPC** (MCP
`2024-11-05`). No extra `mcp` Python package is required for the server
prototype.
