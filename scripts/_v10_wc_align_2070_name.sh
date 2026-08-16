#!/usr/bin/env bash
# V10 Wave C retry — align CT103 MODEL_2070_NAME to qwen2.5-coder:7b (env-only).
# CT104 already has 7b. Does not rebuild images.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"

echo "===== CT103 align MODEL_2070_NAME ====="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "BEFORE_HOST=$(grep -E '^MODEL_2070_NAME=' .env)"
CID=$(docker compose ps -q control-plane)
echo "BEFORE_CTR=$(docker exec "$CID" printenv MODEL_2070_NAME)"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
cp -a .env ".env.bak-v10-wc-${STAMP}"
python3 - <<'PY'
from pathlib import Path
p = Path(".env")
text = p.read_text(encoding="utf-8")
old = "MODEL_2070_NAME=qwen2.5-coder:3b"
new = "MODEL_2070_NAME=qwen2.5-coder:7b"
if old not in text:
    raise SystemExit(f"expected {old!r} in .env; refusing to edit")
if text.count(old) != 1:
    raise SystemExit("MODEL_2070_NAME=qwen2.5-coder:3b is not unique; refusing")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("WROTE", new)
PY
echo "AFTER_HOST=$(grep -E '^MODEL_2070_NAME=' .env)"
echo "--- recreate control-plane to pick up env_file (no rebuild) ---"
docker compose up -d --force-recreate --no-deps control-plane
echo "--- wait ready ---"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 3 http://127.0.0.1:8080/healthz >/dev/null 2>&1; then
    echo "healthz_ok attempt=$i"
    break
  fi
  sleep 2
done
CID=$(docker compose ps -q control-plane)
echo "AFTER_CTR=$(docker exec "$CID" printenv MODEL_2070_NAME)"
echo "AFTER_URL=$(docker exec "$CID" printenv MODEL_2070_BASE_URL)"
echo "--- /readyz redis/state ---"
curl -sS -m 5 http://127.0.0.1:8080/readyz | python3 -c "import json,sys; d=json.load(sys.stdin); print('ready=',d.get('ready')); print('redis=',(d.get('redis') or {}).get('status')); print('state=',(d.get('state') or {}).get('status'))"
echo "V10_WC_ALIGN_CT103_DONE"
EOS

echo "===== CT104 confirm (no edit) ====="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "HOST=$(grep -E '^MODEL_2070_NAME=' .env)"
CID=$(docker compose -f docker-compose.ct104.yml ps -q worker-rlm-root)
echo "CTR=$(docker exec "$CID" printenv MODEL_2070_NAME)"
echo "URL=$(docker exec "$CID" printenv MODEL_2070_BASE_URL)"
if [ "$(grep -E '^MODEL_2070_NAME=' .env)" != "MODEL_2070_NAME=qwen2.5-coder:7b" ]; then
  echo "CT104_HOST_MISMATCH"
  exit 1
fi
if [ "$(docker exec "$CID" printenv MODEL_2070_NAME)" != "qwen2.5-coder:7b" ]; then
  echo "CT104_CTR_MISMATCH"
  exit 1
fi
echo "V10_WC_ALIGN_CT104_OK"
EOS
