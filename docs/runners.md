# Runner lanes

## Gitea Actions runners (act_runner)

| Label | Host | Purpose |
|-------|------|---------|
| docker-ci | CT102 steelleg | CI for target repos and `agent-control-plane` tests |
| deploy | CT102 steelleg | `agent-control-plane` deploy only (SSH to CT103) |

CT103 has **no runner**. Target-repo workflows use **`docker-ci` only**.

Never run privileged agent logic or autonomous agent loops on `docker-ci` or `deploy` beyond scoped deploy jobs.

## CT102 runner setup (split users — 2026-07-20)

CT102 LXC `gitea-runner` (`192.168.4.70`). Two Linux users + two containers:

| User | Container | Labels | Data |
|------|-----------|--------|------|
| `runner-ci` | `act_runner_ci` | `ubuntu-latest`, `docker-ci` | `/opt/act-runner-ci/data` |
| `runner-deploy` | `act_runner_deploy` | `deploy` | `/opt/act-runner-deploy/data` |

Both still use the shared host Docker socket (residual risk). Combined
`act_runner` / `/opt/act-runner/data` retired to `data.bak-combined`.

```bash
# Example recreate (registration token from Gitea instance admin)
docker run -d --name act_runner_ci --restart unless-stopped \
  --user "$(id -u runner-ci):$(id -g runner-ci)" \
  --group-add "$(getent group docker | cut -d: -f3)" \
  -e GITEA_INSTANCE_URL=https://git.ham-sup-lo.com \
  -e GITEA_RUNNER_REGISTRATION_TOKEN=<TOKEN> \
  -e GITEA_RUNNER_NAME=ct102-ci \
  -e GITEA_RUNNER_LABELS='ubuntu-latest:docker://node:20-bookworm,docker-ci:docker://catthehacker/ubuntu:act-latest' \
  -e CONFIG_FILE=/data/config.yaml \
  -v /opt/act-runner-ci/data:/data \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gitea/act_runner:0.6.1
# Mirror for act_runner_deploy with labels deploy-only and /opt/act-runner-deploy/data
```

# Trust boundaries (V4.1.1 ADR-0008)

| Label | Secrets exposure | Isolation claim |
|-------|------------------|-----------------|
| `docker-ci` | No deploy or runtime secrets | Scheduling lane + separate Linux user |
| `deploy` | `DEPLOY_*` only when workflow references them | Scheduling lane + separate Linux user |

**Named boundary:** *CT102 scheduling and credential-domain split* — **not** a strong
principal boundary while both runners share a Docker host/daemon. See
[adr/0008-ct102-scheduling-credential-domain.md](adr/0008-ct102-scheduling-credential-domain.md).

Runtime secrets stay on CT103 `.env` and never enter CI. See [secrets-boundaries.md](secrets-boundaries.md).

### Negative authorization checks (ops)

1. PR CI uses `docker-ci` only (`ci.yaml`) — pass.
2. PR with `runs-on: deploy` **did schedule** on `ct102-deploy` (PR #24 / run 567) —
   remain operational-separation-only; do not claim principal isolation.
3. Deploy workflows run only from protected `main` / `workflow_dispatch`.
4. Cross-user deny: `runner-ci` cannot read `/opt/act-runner-deploy/data/.runner`.
5. Neg probe env had `NO_DEPLOY_SECRETS_IN_ENV` (secrets not referenced).
6. Deploy runner healthy after split (`ct102-deploy` labels `[deploy]`).

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
