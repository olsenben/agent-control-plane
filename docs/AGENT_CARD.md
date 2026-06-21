# Agent card

Product-style transparency document for the homelab coding-agent control plane. Inspired by the [MIT AI Agent Index](https://aiagentindex.mit.edu/) — document the agent like a product, not a script.

Machine-readable companion: [agent-card.json](../agent-card.json) (generated/maintained alongside this file).

## Identity

| Field | Value |
|-------|-------|
| **Agent name** | `ai-sdlc-lab-control-plane` |
| **Version** | See `agentctl version` / git tag on CT103 deploy |
| **Operator** | Homelab (single-tenant) |
| **Control surface** | Gitea issue/PR comments (`/agent …`) |
| **Governance host** | CT103 (`agent-control-plane`) |
| **Execution host** | CT104 (`agent-worker`) |
| **CI truth** | CT102 Gitea Actions (`docker-ci`) |

## Supported commands

| Command | Autonomy | Repo access | Memory write | Gitea comment | Human approval |
|---------|----------|-------------|--------------|---------------|----------------|
| `/agent inspect` | Risk 0 — auto-run | Read-only clone | No | Yes | None |
| `/agent explain` | Risk 0 — auto-run | Read-only clone | No | Yes | None |
| `/agent review` | Risk 1 — auto-run | Read-only clone | Yes (selective) | Yes | None |
| `/agent plan` | Risk 1 — auto-run | Read-only clone | Yes (selective) | Yes | None |
| `/agent fix` | Risk 2 — gated | Branch write only | Yes | Yes | Required before execution |
| deploy / migrate / secrets | Risk 3 | — | — | — | **Blocked by default** |

Detail: [POLICY_GATES.md](POLICY_GATES.md).

## Allowed tools (by worker)

### CT104 `worker-rlm-root`

- `git clone` / `git fetch` (read-only credentials)
- `git diff`, file read within worktree
- Model inference (3080 primary; 2070 memory compression when enabled)
- Session artifact write (run dir only)
- Structured output validation

### CT104 `worker-report`

- Gitea issue/PR comment API (`GITEA_AGENT_TOKEN`, `write:issue`)
- Result inbox write (`agent-state/inbox/ct104-results/`)

### CT103

- Webhook intake, event append, reducer, dispatch
- Memory writeback (SQLite), graph snapshot queries
- Policy gate evaluation, risk tag attachment
- No direct repo mutation

## Write permissions

| Resource | CT103 | CT104 read workflows | CT104 fix (gated) |
|----------|-------|----------------------|-------------------|
| `agent-state` events | Append (reducer) | Read via mount | Read |
| Memory DB | Read/write | No | No |
| Target repo | No | Read-only clone | Agent branch only |
| `main` / protected branches | No | No | **Never** |
| Gitea comments | Via ingest path | Via worker-report | Via worker-report |

## Model endpoints

| Tier | Host | Default model | Role |
|------|------|---------------|------|
| 3080 | Tailscale Ollama | `qwen2.5-coder:14b` | Review, plan, patch reasoning |
| 2070 | Tailscale Ollama | `qwen2.5-coder:7b` | Memory compression, retrieval hints |
| Fake | In-process | `FakeRLMEngine` | CI/offline tests |

Routing: `MODEL_ROUTING_POLICY` in CT104 `.env`.

## Memory sources

| Source | Owner | Used for |
|--------|-------|----------|
| Event ledger (`agent-state/events/`) | CT103 | Audit, replay |
| Trajectory memory (SQLite) | CT103 | Prior runs, rejected hypotheses |
| Cross-repo intelligence graph | CT103 | Blast-radius, affected tests/services |
| ADR compiler output | CT103 | Architecture constraints |
| Tree-sitter / FTS5 index | CT103 | Symbol and text retrieval |

Schema: [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md).

## Approval requirements

```text
Risk 0 (inspect/explain):     none
Risk 1 (review/plan):         none; structured output required
Risk 2 (fix):                 explicit human approval before dispatch
Risk 3 (deploy/secrets):      blocked unless one-off override + manual verification
```

Fix approval is recorded as a CT103 event (`human.approval_granted`).

## Known limitations

- Single-tenant homelab; no multi-org isolation
- Graph indexer MVP covers subset of node/edge types (see [graph-indexer.md](graph-indexer.md))
- Model findings are **hypotheses** until CT102 CI + human verification
- No autonomous merge to protected branches
- MCP write tools not exposed; read-only MCP state server is future-only
- AgentFacts signing not yet implemented (planned: AgentFacts-lite)

## Safety tests

| Test area | Location | Status |
|-----------|----------|--------|
| Prompt injection guards | `tests/test_prompt_injection.py` | Passing |
| Public surface restriction | `tests/test_webhook_*` | Passing |
| Dispatch payload validation | `tests/test_dispatch_payload.py` | Passing |
| Structured output validation | `tests/test_fake_review_run.py`, engine layer | Slice 1 passing |
| Policy gate unit tests | target | Not yet |
| Graph blast-radius smoke | `tests/test_graph_blast_radius.py`, CT103 live | Verified 2026-06-18 |
| Plan structured output | `tests/test_fake_plan_run.py`, engine layer | Plan MVP |

Run: `pytest -q` in `agent-control-plane`.

## Verification invariant

No model output is considered true until validated by:

1. Deterministic checks (schema, policy, closed-world diff gate)
2. Tests (unit/integration in repo)
3. CT102 CI (authoritative)
4. Human approval where required (Risk 2+)

Model self-review is **not** an acceptance gate.

## Last verified

| Milestone | Date (UTC) | Evidence |
|-----------|------------|----------|
| Inspect MVP end-to-end | 2026-06-14 | Homelab runbook + ingest |
| Review Slice 1 (structured comment) | 2026-06-17 | `agent-control-plane` issue #3; run `run-d91435838f457716cb443736c4cc3c6b`; README in files inspected, blast-radius stub |
| Review MVP (graph + context-pack) | 2026-06-18 | CT103 snapshot + blast-radius; `/agent review` on issue #2/#3 |
| Plan MVP (structured comment) | 2026-06-21 | issue #2; `plan_result.v1` + `/agent plan` on official engine (`run-425a2cbe…`, `run-bde99cf…`) |
| Memory 4A writeback | 2026-06-20 | issue #2; review run `run-f32dd48059abccc08338352894b886f3`; `agentctl memory show` |
| Memory 4B retrieval | 2026-06-21 | issue #2; plan run `run-bde99cf06bff485fec153c89a7841150`; `prior_memory_used` + `memory_retrieval` in audit |

Dates are UTC as recorded on CT103/CT104 at ingest time.

Update this table when milestones are verified on CT103+CT104.
