#!/usr/bin/env bash
# Pin both hosts to origin/main tip (docs-ahead OK; no mandatory rebuild if tree match).
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:-c3b3fb4}"
TIP="${TIP:0:7}"

for HOST in 192.168.4.62 192.168.4.63; do
  echo "=== Pin $HOST to $TIP ==="
  ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" "deploy@$HOST" bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
bash scripts/deploy-git-pull.sh
HEAD=\$(git rev-parse --short=7 HEAD)
echo "HEAD=\$HEAD"
case "\$HEAD" in
  $TIP*) ;;
  *) echo TIP_MISMATCH; exit 1 ;;
esac
git log -1 --oneline
EOS
done

# CT103: rebuild only if image lacks bakeoff (already on 234e248+) — restart control-plane to pick docs
ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" deploy@192.168.4.62 bash <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
# Docs-only tip: no image rebuild required; confirm feature modules still import
CID=$(docker compose ps -q control-plane)
docker compose exec -T control-plane python -c "from agent_control.bakeoff_profiles import PROFILE_IDS; assert len(PROFILE_IDS)==4" </dev/null
curl -sf http://127.0.0.1:8080/readyz >/dev/null
echo CT103_PIN_OK
EOS

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 \
  'cd /opt/ai-sdlc-lab/agent-control-plane && echo CT104_PIN_OK $(git rev-parse --short=7 HEAD)'

echo "HOSTS_PINNED tip=$TIP"
