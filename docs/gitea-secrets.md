# Gitea repo secrets (agent-control-plane)

Add under **Settings → Actions → Secrets** for this repo only.

## Required for deploy workflow (CT103)

| Secret | Value |
|--------|-------|
| `DEPLOY_SSH_KEY` | Full private key (OpenSSH format, including BEGIN/END lines) |
| `DEPLOY_HOST` | `192.168.4.62` |
| `DEPLOY_USER` | `deploy` |

## Required for deploy-ct104 workflow (CT104)

| Secret | Value |
|--------|-------|
| `DEPLOY_CT104_SSH_KEY` | Full private key (may reuse CT103 keypair) |
| `DEPLOY_CT104_HOST` | CT104 LAN IP (e.g. `192.168.4.63`) |
| `DEPLOY_CT104_USER` | `deploy` |

## Not in Gitea

- Runtime app secrets (`GITEA_BOT_TOKEN`, model keys, etc.) — CT103 `.env` only
- CT104 runtime `.env` — CT104 host only
- HTTPS git token for `git pull` — CT103/CT104 `/home/deploy/.git-credentials`
- Public SSH key for CT102→CT103 — CT103 `/home/deploy/.ssh/authorized_keys`
- Public SSH key for CT102→CT104 — CT104 `/home/deploy/.ssh/authorized_keys`

## Key generation

```bash
ssh-keygen -t ed25519 -N "" -f ./ct103_deploy
```

1. Private (`ct103_deploy`) → Gitea `DEPLOY_SSH_KEY` and optionally `DEPLOY_CT104_SSH_KEY`
2. Public (`ct103_deploy.pub`) → CT103 and CT104 `authorized_keys`
3. Delete local private key after storing in Gitea

CT104-only keypair (optional):

```bash
ssh-keygen -t ed25519 -N "" -f ./ct104_deploy
```

1. Private → Gitea `DEPLOY_CT104_SSH_KEY`
2. Public → CT104 `/home/deploy/.ssh/authorized_keys`
