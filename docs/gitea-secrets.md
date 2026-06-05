# Gitea repo secrets (agent-control-plane)

Add under **Settings → Actions → Secrets** for this repo only.

## Required for deploy workflow

| Secret | Value |
|--------|-------|
| `DEPLOY_SSH_KEY` | Full private key (OpenSSH format, including BEGIN/END lines) |
| `DEPLOY_HOST` | `192.168.4.62` |
| `DEPLOY_USER` | `deploy` |

## Not in Gitea

- Runtime app secrets (`GITEA_BOT_TOKEN`, model keys, etc.) — CT103 `.env` only
- HTTPS git token for `git pull` — CT103 `/home/deploy/.git-credentials`
- Public SSH key for CT102→CT103 — CT103 `/home/deploy/.ssh/authorized_keys`

## Key generation

```bash
ssh-keygen -t ed25519 -N "" -f ./ct103_deploy
```

1. Private (`ct103_deploy`) → Gitea `DEPLOY_SSH_KEY`
2. Public (`ct103_deploy.pub`) → CT103 `authorized_keys`
3. Delete local private key after storing in Gitea
