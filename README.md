# agent-control-plane

Reusable platform for the Gitea agentic SDLC homelab — a **persistent, auditable coding-agent control plane** where trajectory-rich memory and governance improve repeated engineering work.

Owns canonical JSON schemas, `agentctl`, webhook guard, reducer, dispatch, result ingest, ADR compiler, Redis/RQ, Gitea integration, model routing, and CT103 memory (SQLite + FTS5 target). CT104 executes bounded workflows.

**Status:** Inspect MVP done. **Next:** Review MVP (graph + selective memory + policy gates). See `docs/AGENT_CARD.md`, `docs/architecture.md`, V4 §0.5.

## Documentation index

| Doc | Topic |
|-----|-------|
| [AGENT_CARD.md](docs/AGENT_CARD.md) | Agent transparency card |
| [POLICY_GATES.md](docs/POLICY_GATES.md) | Risk 0–3 governance |
| [MEMORY_SCHEMA.md](docs/MEMORY_SCHEMA.md) | Trajectory memory schema |
| [graph-indexer.md](docs/graph-indexer.md) | Cross-repo graph (OSS borrow, CT103-owned) |
| [graph-oss-borrowing.md](docs/research/tool-spikes/graph-oss-borrowing.md) | Tree-sitter, Codebase-Memory, Backstage, Semgrep, … |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Risk tag taxonomy |
| [EVALS.md](docs/EVALS.md) | Evaluation criteria |
| [RUNBOOK_REVIEW_MVP.md](docs/RUNBOOK_REVIEW_MVP.md) | Review MVP verification |

Target repos are thin clients; they declare contract versions via `.agent/contract.yaml` and must not copy schema files from this package.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
agentctl version
pytest -q
```

## Layout

- `src/agent_control/schemas/` — canonical JSON schemas
- `src/agent_control/` — platform modules (webhook, reducer, queue, agents, workflows)
- `docs/` — architecture, security, runner lanes, tool-spike notes

See `BOOTSTRAP.md` for Gitea org setup, `docs/architecture.md` for tiers, `docs/deploy.md` for CT103, `docs/cicd-setup.md` for CT102→SSH→CT103 deploy, `docs/secrets-boundaries.md` for secrets tiers, `docs/agent-worker.md` for the worker tier, and `docs/rlm-runtime.md` for RLM placement and limits.
