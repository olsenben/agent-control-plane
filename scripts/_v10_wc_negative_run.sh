#!/usr/bin/env bash
# V10 Wave C — run the NON-SCORED negative control on CT103 and CT104.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
SRC="/mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_v10_wc_negative_control.py"
OUT="${1:?usage: _v10_wc_negative_run.sh <local-output-json>}"

: > "$OUT"

for HOST in 192.168.4.62 192.168.4.63; do
  scp -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "$SRC" \
    deploy@"$HOST":/tmp/_v10_wc_negative_control.py >/dev/null
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@"$HOST" bash -s >> "$OUT" <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
TIP=$(git rev-parse HEAD)
HOSTNAME_NOW=$(hostname)
if [ -f docker-compose.ct104.yml ] && [ "$HOSTNAME_NOW" = "agentworker" ]; then
  CID=$(docker compose -f docker-compose.ct104.yml ps -q worker-rlm-root)
else
  CID=$(docker compose ps -q control-plane)
fi
docker cp /tmp/_v10_wc_negative_control.py "${CID}:/tmp/_v10_wc_negative_control.py"
echo "===== ${HOSTNAME_NOW} (${TIP}) ====="
docker exec -e V10_WC_TIP="${TIP}" -e V10_WC_HOST="${HOSTNAME_NOW}" \
  "${CID}" python3 /tmp/_v10_wc_negative_control.py </dev/null
EOS
done

echo "wrote ${OUT}"
