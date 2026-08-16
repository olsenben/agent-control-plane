#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set +e
echo "--- tailscale ping msi ---"
timeout 20 tailscale ping -c 2 100.125.235.54 2>&1 | head -5
echo "--- MagicDNS resolve ---"
getent hosts msi.tail25fd47.ts.net || echo "no magicdns record"
echo "--- LAN scan :11434 on 192.168.4.0/24 ---"
for i in $(seq 1 254); do
  ip="192.168.4.$i"
  ( timeout 1 bash -c "echo > /dev/tcp/$ip/11434" 2>/dev/null && echo "OPEN $ip:11434" ) &
done
wait
echo "--- scan done ---"
EOS
