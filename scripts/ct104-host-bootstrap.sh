#!/usr/bin/env bash
# Bootstrap CT104 agent-worker on steelleg. Run once as root.
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ai-sdlc-lab/agent-control-plane}"
RUNS_DIR="${RUNS_DIR:-/mnt/agent-runs}"
CACHE_DIR="${CACHE_DIR:-/mnt/agent-cache}"
STATE_DIR="${STATE_DIR:-/mnt/agent-state}"
REPO_URL="${REPO_URL:-http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
# CT103 Tailscale IP — replace after CT103 install (see docs/tailscale-acl.example.json)
CT103_TAILSCALE_IP="${CT103_TAILSCALE_IP:-100.96.53.125}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

apt-get update
apt-get install -y git curl python3 docker-compose-plugin nfs-common

if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

mkdir -p "$(dirname "$DEPLOY_DIR")" "$RUNS_DIR" "$CACHE_DIR"
chown -R "$DEPLOY_USER:docker" "$(dirname "$DEPLOY_DIR")" "$RUNS_DIR" "$CACHE_DIR"

sudo -u "$DEPLOY_USER" git config --global url."${REPO_URL%/*}/".insteadOf "git@git.ham-sup-lo.com:"
sudo -u "$DEPLOY_USER" git config --global url."${REPO_URL%/*}/".insteadOf "ssh://git@git.ham-sup-lo.com/"

if [ ! -d "$DEPLOY_DIR/.git" ]; then
  sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$DEPLOY_DIR"
else
  echo "Deploy dir already cloned: $DEPLOY_DIR"
  sudo -u "$DEPLOY_USER" git -C "$DEPLOY_DIR" remote set-url origin "$REPO_URL"
fi

if [ ! -f "$DEPLOY_DIR/.env" ]; then
  cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
  {
    echo ""
    echo "# CT104 overrides (edit CT103_TAILSCALE_IP if needed)"
    echo "REDIS_URL=redis://${CT103_TAILSCALE_IP}:6379/0"
    echo "AGENT_RUNS_HOST_PATH=${RUNS_DIR}"
    echo "AGENT_CACHE_HOST_PATH=${CACHE_DIR}"
    echo "AGENT_STATE_HOST_PATH=${STATE_DIR}"
    echo "MODEL_ROUTING_POLICY=fake"
  } >> "$DEPLOY_DIR/.env"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR/.env"
  chmod 600 "$DEPLOY_DIR/.env"
  echo "Created $DEPLOY_DIR/.env — verify REDIS_URL and NFS mount for agent-state."
fi

chown -R "$DEPLOY_USER:docker" "$DEPLOY_DIR"

cat >&2 <<EOF
Next steps (manual):
  1. Install Tailscale; assign tag:agent-worker in admin console
  2. Mount shared agent-state from CT103 (NFS example):
       echo "192.168.4.62:${STATE_DIR} ${STATE_DIR} nfs defaults,_netdev 0 0" >> /etc/fstab
       mount -a
     Or export from CT103 and mount by Tailscale IP if preferred.
  3. Configure HTTP(S) git token for $DEPLOY_USER (no SSH :22):
       sudo GITEA_DEPLOY_TOKEN=<token> bash scripts/configure-deploy-git-https.sh
     Or HTTPS public URL:
       sudo GITEA_GIT_BASE=https://git.ham-sup-lo.com GITEA_DEPLOY_TOKEN=<token> \\
         bash scripts/configure-deploy-git-https.sh
  4. Add CT102 deploy public key to /home/$DEPLOY_USER/.ssh/authorized_keys
  5. sudo bash scripts/ct104-ufw.sh
  6. Verify Redis from CT103:
       redis-cli -h ${CT103_TAILSCALE_IP} ping
  7. cd ${DEPLOY_DIR} && docker compose -f docker-compose.ct104.yml up -d --build
  8. bash scripts/verify-ct104.sh
  9. Set Gitea secrets DEPLOY_CT104_* for deploy-ct104 workflow
EOF
