# Runner lanes

## Gitea Actions runners (act_runner)

| Label | Host | Purpose |
|-------|------|---------|
| agent-control | CT103 (192.168.4.62) | `agent-control-plane` repo CI + deploy only |
| docker-ci | CT102 steelleg | **Authoritative CI** for target repos (`demo-app`, etc.) |

Target-repo workflows use **`docker-ci` only**. Never run privileged agent logic or autonomous agent loops on `agent-control` or `docker-ci`.

## Not Gitea runners

| Tier | Host | Purpose |
|------|------|---------|
| agent-worker (planned) | CT on steelleg/ironhead | Dequeue RQ jobs, run Aider/OpenHands, call Ollama over Tailscale — see [agent-worker.md](agent-worker.md) |
| GPU inference | buttholecentral / msi | Ollama `:11434` only — **no** repo clone, **no** act_runner for agent sandboxes |

Logical queue names (`planner-3080`, `worker-2070`, …) refer to **which model endpoint** the agent-worker uses, not act_runner labels on GPU PCs.

## CT102 `docker-ci` outbound (no inbound)

Verification runner only — does **not** need Ollama for normal CI:

- `https://git.ham-sup-lo.com` (or LAN `http://192.168.4.60:3000`)

Optional: `http://192.168.4.62:8080/readyz` for integration smoke tests.

See [deploy.md](deploy.md) for UFW and registration.

## Other lanes (out of scope until final stack)

Do not register these until CT103 + CT104 agent-worker + CT102 CI path is stable:

| Label | Purpose |
|-------|---------|
| preview | Ephemeral preview environments |
| danger-lab | Isolated research / high-risk experiments |

No hybrid substitute using `danger-lab` on GPU hosts instead of CT104.
