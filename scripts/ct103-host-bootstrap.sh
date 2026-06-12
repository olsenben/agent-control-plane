#!/usr/bin/env bash
# Bootstrap CT103 as deploy target (no act_runner). Run once as root.
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ai-sdlc-lab/agent-control-plane}"
STATE_DIR="${STATE_DIR:-/mnt/agent-state}"
REPO_URL="${REPO_URL:-http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git}"
STATE_REPO_URL="${STATE_REPO_URL:-http://192.168.4.60:3000/ai-sdlc-lab/agent-state.git}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

apt-get update
apt-get install -y git curl python3 python3-pip python3-venv docker-compose-plugin

if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

mkdir -p "$(dirname "$DEPLOY_DIR")" "$STATE_DIR"
chown -R "$DEPLOY_USER:docker" "$(dirname "$DEPLOY_DIR")"

sudo -u "$DEPLOY_USER" git config --global url."${REPO_URL%/*}/".insteadOf "git@git.ham-sup-lo.com:"
sudo -u "$DEPLOY_USER" git config --global url."${REPO_URL%/*}/".insteadOf "ssh://git@git.ham-sup-lo.com/"

if [ ! -d "$DEPLOY_DIR/.git" ]; then
  sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$DEPLOY_DIR"
else
  echo "Deploy dir already cloned: $DEPLOY_DIR"
  sudo -u "$DEPLOY_USER" git -C "$DEPLOY_DIR" remote set-url origin "$REPO_URL"
fi

if [ ! -d "$STATE_DIR/.git" ]; then
  git clone "$STATE_REPO_URL" "$STATE_DIR"
else
  echo "State dir already cloned: $STATE_DIR"
fi

if [ ! -f "$DEPLOY_DIR/.env" ]; then
  cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR/.env"
  chmod 600 "$DEPLOY_DIR/.env"
  echo "Created $DEPLOY_DIR/.env from .env.example — edit secrets out-of-band."
fi

chown -R "$DEPLOY_USER:docker" "$DEPLOY_DIR"

cat >&2 <<EOF
Next steps (manual):
  1. Edit $DEPLOY_DIR/.env with runtime secrets
  2. Configure HTTP(S) git token for $DEPLOY_USER (no SSH :22):
       sudo GITEA_DEPLOY_TOKEN=<token> bash scripts/configure-deploy-git-https.sh
  3. Add CT102 deploy public key to /home/$DEPLOY_USER/.ssh/authorized_keys
  4. sudo bash scripts/ct103-ufw.sh
EOF
