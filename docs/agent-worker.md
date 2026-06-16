# Agent worker (planned VM/CT)

Separate from **CT102 `docker-ci`**. Runs autonomous loops including **RLM**, Aider, and OpenHands. CT102 remains the **authoritative CI verifier** only.

**Rollout:** final four-tier stack only — [deploy.md](deploy.md#rollout-no-hybrid).  
**RLM detail:** [rlm-runtime.md](rlm-runtime.md).  
**RLM-first adapters:** [ct104-rlm-first-adapter-plan.md](ct104-rlm-first-adapter-plan.md) — RLM orchestrates; Aider/OpenHands are bounded tools, not CT104 replacements.

## Role in the stack

```text
Gitea (source of truth)
    |
    v
CT103 agent-control
  webhook, Redis/RQ, durable task state, reducer/dispatcher
  no repo execution, no RLM REPL
    |
    v
agent-worker VM/CT (e.g. CT104 on steelleg)
  dequeue task, clone repo / worktrees
  RLM runtime OR Aider/OpenHands/custom
  isolated REPL/sandbox (DockerREPL — not host exec)
  recursive subcalls -> GPU OpenAI-compatible APIs over Tailscale
  quick local checks (non-authoritative)
  push branch, Gitea comments
    |
    v
CT102 docker-ci
  Gitea Actions: lint/test/build truth on pushed branches
```

## Trust boundaries

| Tier | Repo / REPL code? | Model inference? | CI truth? |
|------|-------------------|------------------|-----------|
| CT103 agent-control | No | Probe only (`/readyz`) | No |
| **agent-worker** | **Yes** (sandboxed) | Client to GPU APIs | No |
| CT102 docker-ci | CI job only | No | **Yes** |
| GPU hosts | **No** | Serve Ollama/vLLM | No |

**Never:** RLM or agent sandboxes on CT103, GPU Windows hosts, or Proxmox host OS.

## Placement (final only)

| Workload | Host type |
|----------|-----------|
| Aider-style agents | Isolated **CT** on steelleg may suffice |
| **RLM** (REPL + recursive subcalls) | Prefer **VM** on steelleg for nested Docker/Podman sandbox |

Single worker site: **steelleg** (e.g. CT104 or VM `agent-worker`). No parallel hybrid workers on ironhead or GPUs.

## Provisioning

### agent-worker (RLM-oriented)

| Resource | Start here |
|----------|------------|
| CPU | 4–8 vCPU |
| RAM | **16 GB** (8 GB minimum for light Aider-only) |
| Disk | 100–200 GB |
| Swap | 4–8 GB |

### CT103 (reference — not this doc)

Control plane stays small: 2–4 vCPU, 4–8 GB RAM, 20–40 GB disk — see [deploy.md](deploy.md).

Network (outbound from agent-worker):

- LAN: Gitea
- Tailscale: GPU `100.107.20.28`, `100.125.235.54` (Ollama `/v1` or vLLM later)
- Internet: only if dependency installs required

Secrets: scoped `GITEA_BOT_TOKEN`, git credentials — **no** Gitea admin token on worker.

## Sandboxing checklist

- [ ] RLM uses **DockerREPL** or remote sandbox (Modal, E2B, etc.) — not default local `exec` REPL
- [ ] One sandbox boundary per job (or per recursion subtree policy)
- [ ] CT103 enforces recursion/subcall/wall-clock limits ([rlm-runtime.md](rlm-runtime.md))
- [ ] GPU hosts expose inference only (`OLLAMA_HOST=<tailscale-ip>:11434`)

## Quick checks vs CI

Worker may run targeted smoke tests before push; **CT102** runs full project CI. The agent is not the judge.

## Implementation status

**CT104 deployed (2026-06-14).** Inspect MVP verified: webhook dispatch, official RLM, HTTP git clone, Gitea comments.

Still requires for full V4 MVP:

1. [x] CT103 live (API + Redis + state)
2. [x] Real RQ dispatch + job limits
3. [x] Section 1.3 webhooks (bot token API client still stub)
4. [ ] Sandbox + runtime choice beyond read-only inspect
5. [x] OpenAI-compatible URLs to Ollama phase 1

Queue lanes (`planner-3080`, `rlm-3080`, `worker-2070`, …) select **which GPU endpoint** the worker calls — not where repo code runs.
