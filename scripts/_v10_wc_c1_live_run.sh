#!/usr/bin/env bash
# V10 Wave C — run the NON-SCORED live C1 smoke inside the CT103 control-plane.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
SRC="/mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_v10_wc_c1_live_smoke.py"
OUT="${1:?usage: _v10_wc_c1_live_run.sh <local-output-json>}"

scp -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "$SRC" \
  deploy@192.168.4.62:/tmp/_v10_wc_c1_live_smoke.py >/dev/null

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s > "$OUT" <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
TIP=$(git rev-parse HEAD)
CID=$(docker compose ps -q control-plane)
docker cp /tmp/_v10_wc_c1_live_smoke.py "${CID}:/tmp/_v10_wc_c1_live_smoke.py"
docker compose exec -T \
  -e V10_WC_TIP="${TIP}" \
  -e V10_WC_STATE_ROOT=/tmp/v10-wave-c-state \
  control-plane python3 /tmp/_v10_wc_c1_live_smoke.py </dev/null
EOS

echo "wrote ${OUT}"
