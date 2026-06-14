# Gitea repo secrets (agent-control-plane)

Add under **Settings → Actions → Secrets** for this repo only.

## Secret reference (all deploy workflows)

| Gitea secret | CT103 `deploy.yaml` | CT104 `deploy-ct104.yaml` | Example value |
|--------------|---------------------|---------------------------|---------------|
| `DEPLOY_HOST` | SSH target | — | `192.168.4.62` |
| `DEPLOY_SSH_KEY` | SSH private key | — | `ct103_deploy` private key |
| `DEPLOY_USER` | SSH user | — | `deploy` |
| `DEPLOY_CT104_HOST` | — | SSH target | `192.168.4.63` |
| `DEPLOY_CT104_SSH_KEY` | — | SSH private key | same as CT103 or `ct104_deploy` |
| `DEPLOY_CT104_USER` | — | SSH user | `deploy` |
| `DEPLOY_GIT_TOKEN` | HTTP(S) `git pull` | HTTP(S) `git pull` | Gitea personal access token |
| `DEPLOY_GIT_ORIGIN_URL` | optional clone URL | optional clone URL | `http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git` |

Workflows map host secrets into the remote step as `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY` env vars internally. CT104 reads `DEPLOY_CT104_*` from Gitea, then uses the same variable names over SSH.

Git never uses SSH port 22 to Gitea — only HTTP(S) with `DEPLOY_GIT_TOKEN` via `scripts/deploy-git-pull.sh`.

## Minimum secrets to set

**CT103 only:** `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_USER`, `DEPLOY_GIT_TOKEN`

**CT104 only:** `DEPLOY_CT104_HOST`, `DEPLOY_CT104_SSH_KEY`, `DEPLOY_CT104_USER`, `DEPLOY_GIT_TOKEN`

`DEPLOY_GIT_TOKEN` is one shared secret for both workflows.

## Not in Gitea

- Runtime app secrets (`GITEA_BOT_TOKEN`, model keys, etc.) — CT103 `.env` only
- CT104 runtime `.env` — CT104 host only
- Optional host fallback: `/home/deploy/.git-credentials` (from `configure-deploy-git-https.sh`) if CI token unset — workflows require `DEPLOY_GIT_TOKEN` in Gitea
- Public SSH keys for CT102→CT103/CT104 — `authorized_keys` on each host

## Key generation

```bash
ssh-keygen -t ed25519 -N "" -f ./ct103_deploy
```

1. Private (`ct103_deploy`) → Gitea `DEPLOY_SSH_KEY` and `DEPLOY_CT104_SSH_KEY` (if reusing one key)
2. Public (`ct103_deploy.pub`) → CT103 and CT104 `/home/deploy/.ssh/authorized_keys`
3. Delete local private key after storing in Gitea

CT104-only keypair (optional):

```bash
ssh-keygen -t ed25519 -N "" -f ./ct104_deploy
```

1. Private → Gitea `DEPLOY_CT104_SSH_KEY`
2. Public → CT104 `/home/deploy/.ssh/authorized_keys`
