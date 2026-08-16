#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
for H in 192.168.4.62 192.168.4.63; do
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@"$H" bash -s <<'EOS'
set +e
cd /opt/ai-sdlc-lab/agent-control-plane
echo "host=$(hostname) tip=$(git rev-parse HEAD)"
if [ "$(hostname)" = "agentworker" ]; then
  docker compose -f docker-compose.ct104.yml ps --format '{{.Service}} {{.State}}'
else
  docker compose ps --format '{{.Service}} {{.State}}'
  curl -s -o /dev/null -w 'healthz=%{http_code} ' http://127.0.0.1:8080/healthz
  curl -s -o /dev/null -w 'readyz=%{http_code}\n' http://127.0.0.1:8080/readyz
fi
EOS
done
