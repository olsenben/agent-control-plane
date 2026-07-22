#!/usr/bin/env bash
set -euo pipefail

KEY="${HOME}/.ssh/.ct103_deploy"
APP="/opt/ai-sdlc-lab/agent-control-plane"
EXPECTED="fba0846"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE_PY="${SCRIPT_DIR}/_v9_t07_t08_smoke_remote.py"

echo "=== B. Host tip pin ==="
CT103_TIP=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 "git -C $APP rev-parse HEAD")
CT104_TIP=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 "git -C $APP rev-parse HEAD")
echo "ct103_tip: $CT103_TIP"
echo "ct104_tip: $CT104_TIP"
echo "expected:  $EXPECTED"

CT103_MATCH=no
CT104_MATCH=no
[[ "$CT103_TIP" == "$EXPECTED"* ]] && CT103_MATCH=yes
[[ "$CT104_TIP" == "$EXPECTED"* ]] && CT104_MATCH=yes
echo "ct103_match: $CT103_MATCH"
echo "ct104_match: $CT104_MATCH"

if [[ "$CT103_MATCH" != yes || "$CT104_MATCH" != yes ]]; then
  echo "TIP_MISMATCH: attempting git fetch + checkout $EXPECTED on both hosts"
  for host in 192.168.4.62 192.168.4.63; do
    ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "deploy@${host}" bash -s <<EOS
set -euo pipefail
cd ${APP}
git fetch origin main
git checkout ${EXPECTED}
EOS
  done
  CT103_TIP=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 "git -C $APP rev-parse HEAD")
  CT104_TIP=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 "git -C $APP rev-parse HEAD")
  echo "ct103_tip_after_pin: $CT103_TIP"
  echo "ct104_tip_after_pin: $CT104_TIP"
  CT103_MATCH=no
  CT104_MATCH=no
  [[ "$CT103_TIP" == "$EXPECTED"* ]] && CT103_MATCH=yes
  [[ "$CT104_TIP" == "$EXPECTED"* ]] && CT104_MATCH=yes
  echo "ct103_match_after_pin: $CT103_MATCH"
  echo "ct104_match_after_pin: $CT104_MATCH"

  echo "=== Rebuild control-plane after tip pin (CT103) ==="
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
    "cd $APP && docker compose up -d --build control-plane"
fi

echo ""
echo "=== C. CT103 /readyz ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'curl -sf http://127.0.0.1:8080/readyz; echo'

echo ""
echo "=== C2. Compose services ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  "cd $APP && docker compose ps --format '{{.Service}} {{.State}}'"

echo ""
echo "=== D. T07+T08 decisions/artifacts + CI channel smoke ==="
REMOTE_PY="/tmp/_v9_t07_t08_smoke_remote.py"
scp -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "$SMOKE_PY" "deploy@192.168.4.62:${REMOTE_PY}"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd ${APP}
CID=\$(docker compose ps -q control-plane)
docker cp ${REMOTE_PY} "\${CID}:/tmp/_v9_t07_t08_smoke_remote.py"
docker compose exec -T control-plane python3 /tmp/_v9_t07_t08_smoke_remote.py </dev/null
rm -f ${REMOTE_PY}
EOS
