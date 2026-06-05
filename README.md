# agent-control-plane

Reusable platform for the Gitea agentic SDLC homelab.

Owns canonical JSON schemas, the `agentctl` CLI, FastAPI webhook guard, event-only state reducer, ADR compiler, Redis/RQ job queues, Gitea integration, model routing, and ACI tools.

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
