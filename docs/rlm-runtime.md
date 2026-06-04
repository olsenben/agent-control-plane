# RLM runtime placement

RLMs (recursive LLM / REPL-style agents) fit the four-tier homelab model when the **runtime lives on the agent-worker** and **inference stays on GPU hosts**.

Reference: RLM pattern — `rlm.completion(...)` with context in a REPL, recursive sub-LLM calls from that environment (not host `exec` in production).

## Data flow

```text
Gitea issue/comment
        |
        v
CT103 agent-control
  webhook, queue, durable task state, dispatch
  NO repo execution, NO RLM REPL
        |
        v
agent-worker VM/CT
  repo checkout, worktrees
  RLM / Aider / OpenHands / custom wrapper
  isolated REPL (DockerREPL or equivalent)
  recursive subcalls -> OpenAI-compatible client
        |
        v
GPU hosts (Tailscale)
  Ollama /v1 or vLLM — inference only
        |
        v
agent-worker
  patch, smoke tests, push branch, Gitea comment
        |
        v
CT102 docker-ci
  authoritative CI verification
```

## Who owns what

| Concern | Owner |
|---------|--------|
| Durable job state, webhooks, enqueue | CT103 |
| Recursive reasoning, REPL, tool sandbox | **agent-worker** |
| `llm.completion` / chat API calls | GPU endpoints |
| Branch CI truth | CT102 |

## Sandboxing (required for RLMs)

The default RLM local REPL uses Python `exec` in the host process and shares the host venv — **not for production**.

| OK | Avoid |
|----|--------|
| agent-worker **VM** or hardened CT + **DockerREPL** / Modal / Prime / Daytona / E2B | RLM local REPL on CT103 |
| Podman/Docker sandbox per job | RLM on RTX desktop/laptop |
| Inference-only GPU hosts | Agent code on Proxmox **host** OS |

For **Aider-only** tasks, a well-isolated CT may suffice. For **RLMs** that execute model-generated REPL/tool code, prefer a **small VM** for the agent-worker (cleaner nested sandbox than Docker-in-LXC).

## Model endpoints

| Phase | Backend | Notes |
|-------|---------|--------|
| 1 | Ollama `http://<gpu-tailscale>:11434/v1/...` | Partial OpenAI compatibility; good first target |
| 2 | vLLM OpenAI-compatible on GPU host | If RLM stack needs tighter OpenAI/vLLM semantics |

Agent-worker does **not** need a local GPU unless you run the model on the worker itself (out of scope for this homelab).

Configure tiers in CT103/agent-worker `.env` (see `.env.example`); probes use `/readyz` on CT103.

## Control-plane limits (CT103 + queue)

One Gitea issue can become **many** model calls. Enforce in dispatcher and job payload (implement in later phases):

| Limit | Purpose |
|-------|---------|
| `max_recursion_depth` | Cap RLM subcall tree depth |
| `max_subcalls_per_task` | Cap total sub-LLM invocations |
| `max_wall_clock_seconds` | Kill runaway jobs |
| `max_tokens` / context budget | Cost and VRAM protection |
| GPU endpoint rate limits | Serialize per lane (3080 / 2070 concurrency 1) |
| Per-job logs / traces | Debug and audit |
| Kill switch | Cancel job + revoke worker |
| Checkpoint / resume | Optional; store in agent-state |

Without these, one comment can hold GPU lanes for a long time.

## Sizing

**CT103 agent-control** (orchestration only):

| CPU | RAM | Disk |
|-----|-----|------|
| 2–4 vCPU | 4–8 GB | 20–40 GB |

**agent-worker** (RLM + repos + sandbox):

| CPU | RAM | Disk | Swap |
|-----|-----|------|------|
| 4–8 vCPU | **16 GB** preferred (8 GB minimum) | 100–200 GB | 4–8 GB |

RLM jobs accumulate clones, logs, traces, deps, test artifacts, and embeddings.

**GPU hosts:** sized for inference only (existing RTX 3080 / 2070 roles unchanged).

## V4 plan alignment

V4 `rlm-3080` queue lane maps to **logical role** (which GPU endpoint), not an act_runner on the desktop. Execution stays on agent-worker; CT103 routes planner/reviewer/RLM roles to 3080 URL, worker roles to 2070 URL.

See [agent-worker.md](agent-worker.md) and [deploy.md](deploy.md).
