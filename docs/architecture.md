# Architecture

See `gitea_agentic_sdlc_cursor_step_plan_v4.md` for the full implementation plan.

## Homelab tiers (trust model)

```text
Gitea / NPM
      |
      v
CT103 agent-control (this package, Docker on 192.168.4.62)
  webhook guard -> append event -> reducer/dispatcher (planned)
  Redis/RQ + agent-state ledger
      |
      v
CT10x agent-worker VM/CT (steelleg — docs/agent-worker.md, docs/rlm-runtime.md)
  RLM / Aider / OpenHands in isolated sandbox; recursive subcalls
  Tailscale -> Ollama or vLLM OpenAI-compatible APIs on GPU hosts only
  quick local checks, push branch, Gitea comments
      |
      v
CT102 docker-ci (Gitea Actions — verification only)
  authoritative lint/test/build on pushed branches
```

**GPU hosts (buttholecentral / msi):** Ollama inference over Tailscale only. No untrusted repo execution on gaming PCs.

**Rollout:** no hybrid worker topologies before the final CT103 + CT104 + CT102 + GPU-inference layout is in place.

## Control-plane data flow

```text
Gitea event -> webhook guard -> append event -> event-only reducer
  -> optional snapshot -> ADR compiler -> context capsule
  -> enqueue job on Redis/RQ -> agent-worker executes
  -> closed-world diff gate -> push branch
  -> Gitea Actions CI (CT102) -> verification event -> reducer -> Gitea comment
```

Core rules: agents are stateless; the reducer owns canonical state; target repos are thin clients; schemas live in this package only; **CT102 is CI truth, not the agent-worker**; **RLM REPL runs on agent-worker only**, with sandboxing and recursion limits enforced from CT103.

## RLM vs normal agents

| | Normal agent | RLM worker |
|--|--------------|------------|
| Control | CT103 queues one job | CT103 + depth/subcall/time limits |
| Execution | agent-worker | agent-worker + isolated REPL |
| Inference | GPU Tailscale API | Same; many subcalls per issue |
| Sandbox | Docker per job | **VM or DockerREPL** strongly preferred |

See [rlm-runtime.md](rlm-runtime.md).
