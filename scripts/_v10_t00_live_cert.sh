#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"

echo "=== CT103 ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "TIP=$(git rev-parse HEAD)"
echo "BRANCH=$(git rev-parse --abbrev-ref HEAD)"
docker compose images --digests 2>/dev/null | head -40 || true
echo "---READYZ---"
curl -sf http://127.0.0.1:8080/readyz 2>/dev/null | head -c 2000 || curl -sf http://127.0.0.1:8000/readyz 2>/dev/null | head -c 2000 || echo READYZ_FAIL
echo
echo "---ENV_KEYS---"
docker compose exec -T control-plane sh -c 'env | grep -E "^(GITEA_|FIX_REMOTE|MODEL_|OLLAMA)" | sed "s/=.*/=SET/"' </dev/null 2>/dev/null || echo "control-plane env probe failed"
EOS

echo "=== CT104 ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "TIP=$(git rev-parse HEAD)"
docker compose -f docker-compose.ct104.yml images --digests 2>/dev/null | head -40 || true
echo "---SERVICES---"
docker compose -f docker-compose.ct104.yml ps --format json 2>/dev/null | head -c 4000 || docker compose -f docker-compose.ct104.yml ps || true
echo
echo "---ENV_KEYS---"
# Probe common worker service names; never print secret values
for svc in worker agent-worker coding-worker; do
  if docker compose -f docker-compose.ct104.yml ps --services 2>/dev/null | grep -qx "$svc"; then
    echo "service=$svc"
    docker compose -f docker-compose.ct104.yml exec -T "$svc" sh -c 'env | grep -E "^(GITEA_|FIX_REMOTE|MODEL_)" | sed "s/=.*/=SET/" || true' </dev/null 2>/dev/null || true
  fi
done
echo "---TOKEN_ABSENCE---"
# Fail closed: report if GITEA_*_TOKEN appears in any running container env (name only)
docker compose -f docker-compose.ct104.yml ps -q 2>/dev/null | while read -r cid; do
  names=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$cid" 2>/dev/null | grep -E '^GITEA_.*(TOKEN|PASSWORD)=' | sed 's/=.*/=PRESENT/' || true)
  if [ -n "$names" ]; then
    echo "CONTAINER_HAS_GITEA_SECRET_NAMES"
    echo "$names"
  else
    echo "container_ok_no_gitea_token_names cid=${cid:0:12}"
  fi
done
EOS
