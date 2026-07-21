#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?tip}"
TIP="${TIP:0:7}"
bash /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_wait_tip_57.sh "$TIP"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'curl -sf http://127.0.0.1:8080/observe/repos/ai-sdlc-lab/demo-app | head -c 300; echo'
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/healthz; echo'
echo DEPLOY_SMOKE_V6_T03_PASS tip=$TIP
