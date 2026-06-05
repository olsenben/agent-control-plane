# Runner lanes

## Gitea Actions runners (act_runner)

| Label | Host | Purpose |
|-------|------|---------|
| docker-ci | CT102 steelleg | CI for target repos and `agent-control-plane` tests |
| deploy | CT102 steelleg | `agent-control-plane` deploy only (SSH to CT103) |

CT103 has **no runner**. Target-repo workflows use **`docker-ci` only**.

Never run privileged agent logic or autonomous agent loops on `docker-ci` or `deploy` beyond scoped deploy jobs.

## CT102 runner setup

Container `act_runner` on CT102 with labels `docker-ci,deploy`:

```bash
docker run --rm -it \
  --entrypoint act_runner \
  -v /opt/act-runner/config.yaml:/config.yaml \
  -v /opt/act-runner/data:/data \
  gitea/act_runner:latest \
  register --no-interactive --config /config.yaml \
  --instance https://git.ham-sup-lo.com \
  --token <TOKEN> --name runner-docker-ci-ct102 \
  --labels "docker-ci,deploy"

docker start act_runner
```

## Trust boundaries

| Label | Secrets exposure |
|-------|------------------|
| `docker-ci` | No deploy or runtime secrets |
| `deploy` | `DEPLOY_*` only (repo-scoped) |

Runtime secrets stay on CT103 `.env` and never enter CI. See [secrets-boundaries.md](secrets-boundaries.md).

## Not Gitea runners

| Tier | Host | Purpose |
|------|------|---------|
| agent-worker (planned) | CT on steelleg/ironhead | Dequeue RQ jobs, run Aider/OpenHands — see [agent-worker.md](agent-worker.md) |
| GPU inference | buttholecentral / msi | Ollama `:11434` only — no act_runner |

## CT102 outbound

- `https://git.ham-sup-lo.com` (or LAN `http://192.168.4.60:3000`)
- `ssh deploy@192.168.4.62` (deploy lane)
- `http://192.168.4.62:8080/readyz` (post-deploy health)

See [deploy.md](deploy.md) and [cicd-setup.md](cicd-setup.md).
