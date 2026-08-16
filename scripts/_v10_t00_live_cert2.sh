#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"

echo "=== CT103 DIGESTS + MODEL NAMES ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose images 2>/dev/null || true
echo "---IMAGE_IDS---"
docker compose ps -q 2>/dev/null | while read -r cid; do
  docker inspect -f '{{.Name}} image={{.Config.Image}} id={{.Image}}' "$cid" 2>/dev/null || true
done
echo "---MODEL_NAME_VALUES---"
docker compose exec -T control-plane sh -c 'env | grep -E "^(MODEL_3080_NAME|MODEL_2070_NAME|MODEL_3080_FALLBACK_NAME|MODEL_2070_FALLBACK_NAME|MODEL_3080_EXTERNAL_NAME|MODEL_2070_EXTERNAL_NAME|MODEL_ROUTING_POLICY|FIX_REMOTE_PUBLISH_ENABLED)="' </dev/null
echo "---OLLAMA_3080---"
# Prefer internal health URLs from env if present
M3080=$(docker compose exec -T control-plane sh -c 'printf %s "$MODEL_3080_BASE_URL"' </dev/null)
echo "MODEL_3080_BASE_URL_HOST=$(echo "$M3080" | sed "s#https\?://##;s#/.*##")"
curl -sf "${M3080%/}/api/version" 2>/dev/null || echo OLLAMA_3080_VERSION_FAIL
curl -sf "${M3080%/}/api/tags" 2>/dev/null | head -c 2500 || echo OLLAMA_3080_TAGS_FAIL
echo
echo "---OLLAMA_2070---"
M2070=$(docker compose exec -T control-plane sh -c 'printf %s "$MODEL_2070_BASE_URL"' </dev/null)
echo "MODEL_2070_BASE_URL_HOST=$(echo "$M2070" | sed "s#https\?://##;s#/.*##")"
curl -sf "${M2070%/}/api/version" 2>/dev/null || echo OLLAMA_2070_VERSION_FAIL
curl -sf "${M2070%/}/api/tags" 2>/dev/null | head -c 2500 || echo OLLAMA_2070_TAGS_FAIL
echo
EOS

echo "=== CT104 DIGESTS ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose -f docker-compose.ct104.yml images 2>/dev/null || true
echo "---IMAGE_IDS---"
docker compose -f docker-compose.ct104.yml ps -q 2>/dev/null | while read -r cid; do
  docker inspect -f '{{.Name}} image={{.Config.Image}} id={{.Image}}' "$cid" 2>/dev/null || true
done
echo "---VERIFY_SCRIPT---"
if [ -x scripts/verify-ct104.sh ]; then bash scripts/verify-ct104.sh 2>&1 | tail -30; else echo no_verify_ct104; fi
EOS
