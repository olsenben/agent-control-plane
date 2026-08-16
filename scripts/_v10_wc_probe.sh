#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "=== HOST ==="
hostname
echo "=== GIT TIP ==="
git rev-parse HEAD
echo "=== ENV KEYS (redacted values) ==="
grep -E '^(MODEL_|EXTERNAL_|.*API_KEY|.*FALLBACK|.*GATEWAY)' .env 2>/dev/null | sed -E 's/(KEY|TOKEN|SECRET)=.*/\1=<redacted:set>/' || echo "no .env"
echo "=== COMPOSE PS ==="
docker compose ps --format '{{.Service}} {{.State}}' || true
echo "=== CONTAINER ENV (redacted) ==="
CID=$(docker compose ps -q control-plane)
docker exec "$CID" printenv | grep -E '^(MODEL_|EXTERNAL_|RECURSIVE_)' | sed -E 's/(KEY|TOKEN|SECRET)=(.+)/\1=<redacted:set>/' | sort
EOS
