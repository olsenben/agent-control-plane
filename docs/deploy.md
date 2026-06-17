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

5. On **goldenleg Proxmox host**, create `/srv/agent-state` and bind into CT103 (`mp0`). See [agent-state-storage.md](agent-state-storage.md). Inside CT103, `/mnt/agent-state` is the mount target — clone `agent-state` repo there (bootstrap script does this).
6. Clone `agent-control-plane` to `/opt/ai-sdlc-lab/agent-control-plane`.
7. `cp .env.example .env` and edit secrets (never commit `.env`).

Do **not** install `nfs-kernel-server` on CT103.

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

Share `/mnt/agent-state` with CT103 via host NFS + bind mounts — [agent-state-storage.md](agent-state-storage.md). Keep `/mnt/agent-runs` and `/mnt/agent-cache` local on CT104. CT104 connects to CT103 Redis over Tailscale (`REDIS_URL` in `.env`).

Quick CT103 checks: `bash scripts/verify-ct103.sh`

CT104 CI deploy: `.gitea/workflows/deploy-ct104.yaml` (SSH from CT102, same `agent-control-plane` repo). Quick checks: `bash scripts/verify-ct104.sh`

See [ct104.md](ct104.md) and [cicd-setup.md](cicd-setup.md).

## Homelab status (2026-06-14)

| Component | Host | Status |
|-----------|------|--------|
| Control plane + Redis + worker-state | CT103 `192.168.4.62` | Live |
| worker-rlm-root + worker-report | CT104 `192.168.4.63` | Live |
| CI deploy (`deploy.yaml`, `deploy-ct104.yaml`) | CT102 | Live |
| Webhook → state → dispatch → workers → ingest | CT103 ↔ CT104 | Verified |
| Official inspect + repo clone + Gitea comment | CT104 + Ollama | Verified |
| Public NPM `control.ham-sup-lo.com` | CT101 | Optional / deferred |

**Inspect MVP complete (2026-06-14).** Sharpen memory retrieval, traceability, and policy gates before expanding writes.

## Current targets (2026-06)

See [architecture.md](architecture.md), [AGENT_CARD.md](AGENT_CARD.md), V4 §0.5.

| Priority | Target |
|----------|--------|
| 1 | Smoke-test `/agent explain` |
| 2 | `agentctl graph snapshot` + blast-radius (minimal) |
| 3 | **Review MVP** — review + graph section + selective memory + risk_tags |
| 4 | `/agent plan` (graph-informed CI hints) |
| 5 | Risk 2 `/agent fix` (approval + graph-gated CI matrix) |
| 6 | Branch push + CT102 CI |
| 7+ | AgentFacts-lite, replay console, drift detector |

## Defer until section 1.3+

- [x] `GITEA_WEBHOOK_SECRET` and Gitea webhook registration (LAN `http://192.168.4.62:8080/webhooks/gitea`)
- [x] CI deploy keeps **worker-state** (state queue) in sync via `--profile workers`
- [x] **CT104 agent-worker** provision — see [ct104.md](ct104.md)
- [ ] Scheduled `agentctl results ingest --inbox` on CT103 (optional cron)
- Do **not** run agent sandboxes or RQ repo workers on GPU Windows hosts
