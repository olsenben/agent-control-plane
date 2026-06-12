# CI/CD setup (CT102 → SSH → CT103 / CT104)

## Architecture

```text
Gitea CT100
  → CT102 docker-ci: ci.yaml (lint, test, compose validate)
  → CT102 deploy:    deploy.yaml (test → SSH → CT103 git pull + compose up + /readyz)
  → CT102 deploy:    deploy-ct104.yaml (test → SSH → CT104 git pull + worker compose up)
CT103: control plane only, runtime .env on disk, no act_runner
CT104: agent workers only, runtime .env on disk, no act_runner
```

## Workflows

| File | Trigger | Runner |
|------|---------|--------|
| `.gitea/workflows/ci.yaml` | push, PR | `docker-ci` |
| `.gitea/workflows/deploy.yaml` | push to `main`, manual | `deploy` (test job uses `docker-ci`) |
| `.gitea/workflows/deploy-ct104.yaml` | push to `main`, manual | `deploy` (test job uses `docker-ci`) |

## Gitea repo secrets

Deployment secrets — see [gitea-secrets.md](gitea-secrets.md):

**CT103 (`deploy.yaml`):**

- `DEPLOY_SSH_KEY`
- `DEPLOY_HOST` (`192.168.4.62`)
- `DEPLOY_USER` (`deploy`)

**CT104 (`deploy-ct104.yaml`):**

- `DEPLOY_CT104_SSH_KEY`
- `DEPLOY_CT104_HOST` (e.g. `192.168.4.63`)
- `DEPLOY_CT104_USER` (`deploy`)

Runtime secrets live on each host `.env` — see [secrets-boundaries.md](secrets-boundaries.md).

## CT103 bootstrap (one-time)

```bash
sudo bash scripts/ct103-ufw.sh
sudo bash scripts/ct103-host-bootstrap.sh
sudo nano /opt/ai-sdlc-lab/agent-control-plane/.env
```

### deploy user SSH (CT102 → CT103 / CT104)

1. Generate keypair off-host: `ssh-keygen -t ed25519 -f ./ct103_deploy`
2. Private key → Gitea `DEPLOY_SSH_KEY` (and `DEPLOY_CT104_SSH_KEY` if reusing one key)
3. Public key → `/home/deploy/.ssh/authorized_keys` on CT103 and CT104

### Git pull (HTTPS — SSH git not exposed on :22)

```bash
sudo -u deploy git -C /opt/ai-sdlc-lab/agent-control-plane remote set-url origin \
  http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git

sudo -u deploy git config --global credential.helper store
# echo "http://deploy:TOKEN@192.168.4.60:3000" > /home/deploy/.git-credentials
sudo -u deploy git -C /opt/ai-sdlc-lab/agent-control-plane pull --ff-only origin main
```

## CT102 runner labels

Re-register with `docker-ci,deploy` — see [runners.md](runners.md).

## Verification

```bash
# From Windows or CT102 (temp key file)
ssh -i ./ct103_deploy deploy@192.168.4.62 'echo SSH_OK'

# On CT103
sudo -u deploy git -C /opt/ai-sdlc-lab/agent-control-plane pull --ff-only origin main
curl -s http://127.0.0.1:8080/readyz

# From CT102
curl -s http://192.168.4.62:8080/readyz
```

## Log safety

Deploy workflow does **not** run `docker compose config` on CT103 (it would print runtime `.env` values). Compose validation uses `.env.example` in the CI `test` job only (including the `workers` profile).

On deploy, CT103 runs `docker compose --profile workers build control-plane worker-state` then `up -d`, so **worker-state** is rebuilt with every merge to `main` (not only control-plane).

## CT104 bootstrap (one-time)

```bash
sudo CT103_TAILSCALE_IP=<ct103-ts-ip> bash scripts/ct104-host-bootstrap.sh
sudo bash scripts/ct104-ufw.sh
sudo nano /opt/ai-sdlc-lab/agent-control-plane/.env
```

Git pull and deploy user setup mirror CT103 — same repo path `/opt/ai-sdlc-lab/agent-control-plane`.

## Day-2 flow

```text
PR / push → ci on docker-ci
merge to main → deploy on deploy (CT103) + deploy-ct104 (CT104 workers)
```

Trigger manual deploy: Actions → deploy or deploy-ct104 → Run workflow.

## Acceptance

- [ ] CT102 runner online with `docker-ci` and `deploy`
- [ ] Gitea secrets `DEPLOY_*` set
- [ ] `deploy` user on CT103: SSH, git pull, docker compose
- [ ] `ci` green on PR
- [ ] `deploy` green on `main`
- [ ] `.env` on CT103 unchanged by workflows
