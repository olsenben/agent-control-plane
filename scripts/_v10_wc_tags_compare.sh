#!/usr/bin/env bash
# Compare configured 2070 URL vs 3080 URL from CT103 (ACP-host view).
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
CID=$(docker compose ps -q control-plane)
echo "CTR_MODEL_2070_NAME=$(docker exec "$CID" printenv MODEL_2070_NAME)"
echo "CTR_MODEL_2070_BASE_URL=$(docker exec "$CID" printenv MODEL_2070_BASE_URL)"
echo "CTR_MODEL_3080_NAME=$(docker exec "$CID" printenv MODEL_3080_NAME)"
echo "CTR_MODEL_3080_BASE_URL=$(docker exec "$CID" printenv MODEL_3080_BASE_URL)"
echo "--- 2070 configured URL ---"
curl -sS -m 10 http://100.125.235.54:11434/api/tags
echo
echo "--- 3080 configured URL ---"
curl -sS -m 10 http://100.107.20.28:11434/api/tags
echo
echo "--- tailscale ---"
tailscale status | grep -E 'msi|buttholecentral|100\.125\.235\.54|100\.107\.20\.28'
EOS
