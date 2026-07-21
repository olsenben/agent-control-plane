#!/usr/bin/env bash
set -euo pipefail
KEY="$HOME/.ssh/.ct103_deploy"
for host in 192.168.4.62 192.168.4.63; do
  echo "=== $host ==="
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "deploy@$host" \
    'cd /opt/ai-sdlc-lab/agent-control-plane && git fetch origin main 2>/dev/null; git rev-parse --short=7 HEAD; git rev-parse --short=7 origin/main 2>/dev/null || echo no-origin'
done
