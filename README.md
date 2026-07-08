# agent-control-plane

Reusable platform for the Gitea agentic SDLC homelab — a **persistent, auditable coding-agent control plane** where trajectory-rich memory and governance improve repeated engineering work.

Owns canonical JSON schemas, `agentctl`, webhook guard, reducer, dispatch, result ingest, ADR compiler, Redis/RQ, Gitea integration, model routing, and CT103 memory (SQLite + FTS5 target). CT104 executes bounded workflows.

**Status:** Review + Plan MVP done. **Slice 5–6C** done. **4C + 5.2 + 5.3** homelab signed off (issue #16, 2026-07-06). **6D** homelab pending (issue #17). See `docs/AGENT_CARD.md` and `docs/architecture.md`.

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
| [slice-5-structured-output-hardening.md](docs/slice-5-structured-output-hardening.md) | Structured output boundary (complete) |
| [slice-6b-local-patch-artifact.md](docs/slice-6b-local-patch-artifact.md) | Local patch artifact / fix worker (6B) |
| [slice-6c-closed-world-diff-gate.md](docs/slice-6c-closed-world-diff-gate.md) | Closed-world diff gate (6C) |
| [slice-6d-branch-push-pr.md](docs/slice-6d-branch-push-pr.md) | Branch push + PR (6D) |
| [slice-5.1-engine-reliability.md](docs/slice-5.1-engine-reliability.md) | Engine I/O + parse-failure reporting |
| [slice-4c-result-ingest-automation.md](docs/slice-4c-result-ingest-automation.md) | Event-driven result ingest |
| [slice-5.2-plan-quality-gate.md](docs/slice-5.2-plan-quality-gate.md) | Plan quality gate |
| [slice-5.3-issue-task-backfill.md](docs/slice-5.3-issue-task-backfill.md) | Bare review/plan issue-task backfill |
| [slice-5.2-5.3-bundle-plan.md](docs/slice-5.2-5.3-bundle-plan.md) | 5.2 + 5.3 bundle plan and homelab verification |

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
