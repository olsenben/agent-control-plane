# Secrets boundaries

Three tiers — do not mix them.

| Tier | Where | Examples | Through CI? |
|------|-------|----------|-------------|
| CI secrets | Gitea repo/org secrets | CI-only tokens (if needed later) | `ci.yaml` only |
| Deployment secrets | Gitea repo secrets | `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER` | `deploy.yaml` only; transient in job |
| Runtime secrets | CT103 host `.env` | `GITEA_BOT_TOKEN`, model keys, webhooks | **Never** |

## Deployment secrets

Used for CT102 → CT103 SSH during `deploy.yaml`. Private key is written to a temp file in the job and removed on exit. Not stored on CT102 disk.

See [gitea-secrets.md](gitea-secrets.md).

## Runtime secrets

Live in `/opt/ai-sdlc-lab/agent-control-plane/.env` on CT103. Created at bootstrap from `.env.example`; edited out-of-band. Deploy workflow checks `test -f .env` but does not read or overwrite it.

## Git credentials on CT103

HTTPS pull credentials live on the CT103 `deploy` user (`~/.git-credentials`). Separate from deployment SSH keys. Not in Gitea secrets.

## Rotation

| Secret type | Rotate by |
|-------------|-----------|
| `DEPLOY_SSH_KEY` | New keypair; update Gitea secret + CT103 `authorized_keys` |
| Runtime `.env` | Edit on CT103 host; `docker compose up -d` |
| Git HTTPS token | Update `/home/deploy/.git-credentials` on CT103 |
