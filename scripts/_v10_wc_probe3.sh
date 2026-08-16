#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
for H in 192.168.4.62 192.168.4.63; do
  echo "##### HOST $H #####"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@"$H" bash -s <<'EOS'
set +e
hostname
echo "--- tailscale status (2070/3080) ---"
(tailscale status 2>/dev/null || sudo tailscale status 2>/dev/null || echo "no tailscale cli") | head -30
echo "--- curl 2070 tags from HOST ---"
curl -sS -m 8 http://100.125.235.54:11434/api/tags | head -c 400; echo
echo "curl_exit=$?"
echo "--- curl 3080 tags from HOST ---"
curl -sS -m 8 http://100.107.20.28:11434/api/tags | head -c 200; echo
echo "curl_exit=$?"
EOS
done
