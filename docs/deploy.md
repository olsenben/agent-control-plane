# AgentControl homelab deploy (CT103)

## Rollout: no hybrid

Ship the **final** topology only — no intermediate hybrid layouts.

| Skip until final stack | Final stack includes |
|------------------------|----------------------|
| Agent sandboxes on GPU PCs | CT104 agent-worker on steelleg |
| Multiple worker pools (small + GPU-local + sandbox) | Single agent-worker CT |
| `preview` / `danger-lab` runner lanes | CT102 `docker-ci` verifier only |
| GPU-host `act_runner` for repo work | Ollama inference APIs only |
| Partial “workers on 3080” experiments | RQ consumers on agent-worker only |

**Order:** CT103 control (API + Redis + state) → section 1.3 webhooks → CT103 state RQ worker → **CT104 agent-worker** → enable autonomous jobs. Do not enable half of this on GPU hosts “temporarily.”

Public NPM for `control.ham-sup-lo.com` can wait with the same rule if you want LAN-only until the full stack is up.

## Four-tier model

| Tier | ID | Role |
|------|-----|------|
| Gitea | CT100 | Source of truth |
| agent-control (app) | CT103 `192.168.4.62` | Webhook, Redis, state, dispatch (no repo sandboxes, no runner) |
| agent-worker | CT104 or VM (steelleg) | RLM/Aider sandbox — [agent-worker.md](agent-worker.md), [rlm-runtime.md](rlm-runtime.md) |
| docker-ci | CT102 steelleg | Gitea Actions verification only |
| GPU | buttholecentral / msi | Ollama inference over Tailscale only |

**CT102 is not the agent-worker.** Do not run Aider/OpenHands autonomous loops on `docker-ci`.

Option A: AgentControl on **CT103**, Gitea **CT100**, NPM **CT101**, verifier **CT102** on steelleg (`192.168.4.51`, Tailscale `100.90.26.38`).

## Addresses

| Component | LAN | Tailscale |
|-----------|-----|-----------|
| Gitea CT100 | 192.168.4.60 | via goldenleg |
| NPM CT101 | 192.168.4.61 | via goldenleg |
| Runner CT102 | 192.168.4.51+ (LXC on steelleg) | 100.90.26.38 |
| AgentControl CT103 | **192.168.4.62** | assign on install |
| Ollama 3080 | — | 100.107.20.28:11434 |
| Ollama 2070 | — | 100.125.235.54:11434 |

LAN webhook URL (section 1.3): `http://192.168.4.62:8080/webhooks/gitea`

Public URL (optional): `https://control.ham-sup-lo.com` via NPM.

## CT103 sizing (control only)

Orchestration does not run RLM REPL or repo sandboxes:

| CPU | RAM | Disk |
|-----|-----|------|
| 2–4 vCPU | 4–8 GB | 20–40 GB |

Agent-worker sizing (16 GB RAM, VM preferred for RLM): [agent-worker.md](agent-worker.md), [rlm-runtime.md](rlm-runtime.md).

## CT103 provisioning (manual)

1. Create LXC **CT103** on goldenleg, static `192.168.4.62/22`.
2. Install Docker Engine + Compose plugin.
3. Install Tailscale; assign **`tag:agent-control`** in admin console.
4. UFW:

```bash
sudo ufw default deny incoming
sudo ufw allow from 192.168.4.0/22 to any port 8080 proto tcp
sudo ufw deny 6379/tcp
sudo ufw enable
```

5. Create `/mnt/agent-state` and clone `agent-state` repo.
6. Clone `agent-control-plane` to `/opt/ai-sdlc-lab/agent-control-plane`.
7. `cp .env.example .env` and edit secrets (never commit `.env`).

## First deploy

```bash
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose config
docker compose up -d --build
curl -s http://127.0.0.1:8080/healthz
curl -s http://127.0.0.1:8080/readyz
```

Manual bootstrap (CI deploy uses the same profile after webhooks are configured):

```bash
docker compose --profile workers build control-plane worker-state
docker compose --profile workers up -d
```

## Redis persistence

Named volume `redis-data` survives `docker compose down` (without `-v`).

```bash
docker compose exec redis redis-cli SET deploy:test ok
docker compose restart redis
docker compose exec redis redis-cli GET deploy:test
```

Backup example:

```bash
docker run --rm -v agent-control-plane_redis-data:/data -v /backup:/backup alpine \
  tar czf /backup/redis-$(date +%F).tgz -C /data .
```

## GPUs offline

- `/healthz` — always OK if process up.
- `/readyz` — **200** `degraded` when Redis + state OK but Ollama unreachable.
- `/readyz?strict=true` — **503** if configured GPU down.
- `/readyz` also reports optional external/fallback endpoint probes (informational only).
- `agentctl model ping --role planner` — exit 1 when unreachable (uses tier fallback if enabled).
- `agentctl model resolve --role planner` — show configured primary provider without probing.
- Webhooks work without GPUs (no model call on webhook path).

## Model external and fallback APIs

Per-tier optional OpenAI-compatible endpoints in `.env`:

- `MODEL_3080_EXTERNAL_*` / `MODEL_2070_EXTERNAL_*` — cloud or proxy URLs for roles listed in `MODEL_EXTERNAL_ROLES`.
- `MODEL_3080_FALLBACK_*` / `MODEL_2070_FALLBACK_*` — used when the role primary is unreachable.
- `MODEL_FALLBACK_ENABLED=false` — fail fast instead of calling fallback APIs (cost control).

GPU primaries still gate `/readyz` degraded vs ready. External/fallback keys must stay in `.env` on CT103 only.

## CT102 runner (docker-ci + deploy)

Docker container `act_runner` on CT102 with labels `docker-ci,deploy`:

- `docker-ci` — CI for target repos and `agent-control-plane` tests
- `deploy` — SSH deploy to CT103 (`agent-control-plane` only)

See [runners.md](runners.md) and [cicd-setup.md](cicd-setup.md).

## CT103 deploy target (no runner)

CT103 runs the app only. CI/CD deploys via CT102 SSH:

```bash
sudo bash scripts/ct103-host-bootstrap.sh
sudo bash scripts/ct103-ufw.sh
```

Runtime secrets in `/opt/ai-sdlc-lab/agent-control-plane/.env` (never through CI).
Deployment secrets in Gitea: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`.

Push to `main` runs `.gitea/workflows/deploy.yaml` (test → SSH → git pull → compose up → `/readyz`).

## Tailscale ACLs

Apply `docs/tailscale-acl.example.json` in Tailscale admin (replace `agentcontrol` IP after CT103 install).

On GPU Windows hosts:

```text
OLLAMA_HOST=<tailscale-ip>:11434
```

## Optional public ingress (NPM)

1. Porkbun: `control.ham-sup-lo.com` -> home IP.
2. NPM proxy -> `http://192.168.4.62:8080`, Let's Encrypt, rate limit ~10 req/s burst 20.

**Preferred:** point Gitea webhooks at LAN `http://192.168.4.62:8080/webhooks/gitea` and restrict public NPM.

Set `ENFORCE_PUBLIC_SURFACE_RESTRICTION=true` on CT103 if the public proxy remains — only `/webhooks/gitea`, `/healthz`, `/readyz` are served.

## CT104 workers (steelleg)

After CT103 webhooks + state worker are live:

1. Re-apply UFW on CT103 so Redis is Tailscale-only: `sudo bash scripts/ct103-ufw.sh`
2. Update Tailscale ACL (`docs/tailscale-acl.example.json`) — `tag:agent-worker` → `agentcontrol:6379`
3. Provision CT104 — see [ct104.md](ct104.md)

On **CT104** (not CT103):

```bash
sudo CT103_TAILSCALE_IP=<ct103-ts-ip> bash scripts/ct104-host-bootstrap.sh
sudo bash scripts/ct104-ufw.sh
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose -f docker-compose.ct104.yml up -d --build
```

Mount `/mnt/agent-runs`, `/mnt/agent-cache`, and NFS-mount `/mnt/agent-state` from CT103. CT104 connects to CT103 Redis over Tailscale (`REDIS_URL` in `.env`).

Quick CT103 checks: `bash scripts/verify-ct103.sh`

See [ct104.md](ct104.md).

## Defer until section 1.3+

- `GITEA_WEBHOOK_SECRET` and Gitea webhook registration
- CI deploy keeps **worker-state** (state queue) in sync via `--profile workers`; **agent-worker** CT is separate
- **agent-worker CT** provision (see [agent-worker.md](agent-worker.md))
- Do **not** run agent sandboxes or RQ repo workers on GPU Windows hosts
