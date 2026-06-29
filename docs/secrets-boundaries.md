# Secrets boundaries

Three tiers — do not mix them.

| Tier | Where | Examples | Through CI? |
|------|-------|----------|-------------|
| CI secrets | Gitea repo/org secrets | CI-only tokens (if needed later) | `ci.yaml` only |
| Deployment secrets | Gitea repo secrets | `DEPLOY_*` (CT103), `DEPLOY_CT104_*` (CT104) | deploy workflows only; transient in job |
| Runtime secrets | CT103/CT104 host `.env` | `GITEA_BOT_TOKEN`, model keys, webhooks | **Never** |

## Deployment secrets

Used for CT102 → CT103/CT104 SSH during `deploy.yaml` and `deploy-ct104.yaml`. Private key is written to a temp file in the job and removed on exit. Not stored on CT102 disk.

See [gitea-secrets.md](gitea-secrets.md).

## Runtime secrets

Live in `/opt/ai-sdlc-lab/agent-control-plane/.env` on each host. Created at bootstrap from `.env.example`; edited out-of-band. Deploy workflows check `test -f .env` but do not read or overwrite it.

### Slice 6D token separation (CT104)

| Token | Host | Scope |
|-------|------|-------|
| `GITEA_AGENT_TOKEN` | CT104 | Issue comments only |
| `GITEA_BOT_TOKEN` | CT104 | Branch `git push` + PR API only; scoped to target repos; **no** admin, repo delete, or org management |

Never use one token for both comment and push. `GITEA_BOT_TOKEN` is required only when `FIX_REMOTE_PUBLISH_ENABLED=true`. See [slice-6d-branch-push-pr.md](slice-6d-branch-push-pr.md).

## Git credentials on deploy hosts

HTTPS pull credentials live on the `deploy` user (`~/.git-credentials`) on CT103 and CT104. Separate from deployment SSH keys. Not in Gitea secrets.

## Rotation

| Secret type | Rotate by |
|-------------|-----------|
| `DEPLOY_SSH_KEY` | New keypair; update Gitea secret + CT103 `authorized_keys` |
| Runtime `.env` | Edit on CT103 host; `docker compose up -d` |
| Git HTTPS token | Update `/home/deploy/.git-credentials` on CT103 |
