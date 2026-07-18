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

### V4.1.1 / Slice 6D.2 — CT103-only Gitea write

| Token | Host | Scope |
|-------|------|-------|
| `GITEA_BOT_TOKEN` | **CT103 only** (`publish-broker` + control-plane comments) | Branch push, PR API, issue comments |
| *(none)* | CT104 | No Gitea write tokens; fail-closed at worker startup |

CT104 may keep a **read-only** checkout credential (`~/.git-credentials`) for clone/fetch. See [slice-6d2-ct103-publish-brokerage.md](slice-6d2-ct103-publish-brokerage.md) and ADR-0004.

Legacy Slice 6D CT104 token placement is retired technical debt — do not restore.

## Git credentials on deploy hosts

HTTPS pull credentials live on the `deploy` user (`~/.git-credentials`) on CT103 and CT104. Separate from deployment SSH keys. Not in Gitea secrets.

## Rotation

| Secret type | Rotate by |
|-------------|-----------|
| `DEPLOY_SSH_KEY` | New keypair; update Gitea secret + CT103 `authorized_keys` |
| Runtime `.env` | Edit on CT103 host; `docker compose up -d` |
| Git HTTPS token | Update `/home/deploy/.git-credentials` on CT103 |
