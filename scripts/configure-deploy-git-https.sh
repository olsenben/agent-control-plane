#!/usr/bin/env bash
# Configure deploy user for git pull over HTTP(S) with token — no SSH :22 to Gitea.
# Usage (root): sudo GITEA_DEPLOY_TOKEN=<token> bash scripts/configure-deploy-git-https.sh
# Or: sudo bash scripts/configure-deploy-git-https.sh <token>
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
GITEA_GIT_BASE="${GITEA_GIT_BASE:-http://192.168.4.60:3000}"
GITEA_GIT_USER="${GITEA_GIT_USER:-deploy}"
TOKEN="${GITEA_DEPLOY_TOKEN:-${1:-}}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

if [ -z "$TOKEN" ]; then
  read -rsp "Gitea HTTP(S) token for ${GITEA_GIT_USER}: " TOKEN
  echo
fi

if [ -z "$TOKEN" ]; then
  echo "Token required." >&2
  exit 1
fi

if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  echo "User ${DEPLOY_USER} does not exist." >&2
  exit 1
fi

HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
CREDS_FILE="${HOME_DIR}/.git-credentials"
BASE_NO_SCHEME="${GITEA_GIT_BASE#http://}"
BASE_NO_SCHEME="${BASE_NO_SCHEME#https://}"

install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "${HOME_DIR}/.config/git"
sudo -u "$DEPLOY_USER" git config --global credential.helper store
printf '%s\n' "${GITEA_GIT_BASE}://${GITEA_GIT_USER}:${TOKEN}@${BASE_NO_SCHEME}" >"$CREDS_FILE"
chown "$DEPLOY_USER:$DEPLOY_USER" "$CREDS_FILE"
chmod 600 "$CREDS_FILE"

echo "Wrote ${CREDS_FILE} for ${GITEA_GIT_BASE} (user ${GITEA_GIT_USER})."
echo "Test: sudo -u ${DEPLOY_USER} git ls-remote ${GITEA_GIT_BASE}/ai-sdlc-lab/agent-control-plane.git HEAD"
