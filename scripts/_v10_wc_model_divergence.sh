#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
for H in 192.168.4.62 192.168.4.63; do
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@"$H" bash -s <<'EOS'
set +e
cd /opt/ai-sdlc-lab/agent-control-plane
echo "===== $(hostname) ====="
if [ "$(hostname)" = "agentworker" ]; then
  CID=$(docker compose -f docker-compose.ct104.yml ps -q worker-rlm-root)
else
  CID=$(docker compose ps -q control-plane)
fi
docker exec "$CID" printenv | grep -E '^MODEL_(2070|3080)_(NAME|BASE_URL)=' | sort
echo "--- .env on host ---"
grep -E '^MODEL_(2070|3080)_(NAME|BASE_URL)=' .env 2>/dev/null | sort
echo "--- .env mtime ---"
stat -c '%y %n' .env 2>/dev/null
EOS
done
