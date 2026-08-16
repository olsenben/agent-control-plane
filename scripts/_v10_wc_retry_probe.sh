#!/usr/bin/env bash
# V10 Wave C retry — 2070 reachability + MODEL_2070_NAME from ACP hosts.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"

probe_host() {
  local ip="$1"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@"$ip" bash -s <<'EOS'
set +e
echo "===== HOST $(hostname) ====="
echo "--- git tip ---"
cd /opt/ai-sdlc-lab/agent-control-plane
git rev-parse HEAD
echo "--- tailscale msi ---"
tailscale status 2>/dev/null | grep -E 'msi|100\.125\.235\.54|buttholecentral|100\.107\.20\.28' || echo "tailscale status unavailable"
echo "--- ping 100.125.235.54 ---"
ping -c 2 -W 3 100.125.235.54 2>&1 | tail -n 6
echo "--- host curl /api/tags ---"
curl -sS -m 12 -w '\nhttp_status=%{http_code} time=%{time_total}\n' http://100.125.235.54:11434/api/tags
echo
echo "--- container env MODEL_2070 ---"
if [ "$(hostname)" = "agentworker" ]; then
  CID=$(docker compose -f docker-compose.ct104.yml ps -q worker-rlm-root)
else
  CID=$(docker compose ps -q control-plane)
fi
docker exec "$CID" printenv | grep -E '^MODEL_2070_(NAME|BASE_URL)=' | sort
echo "--- host .env MODEL_2070 ---"
grep -E '^MODEL_2070_(NAME|BASE_URL)=' .env 2>/dev/null | sort
echo "--- .env mtime ---"
stat -c '%y %n' .env 2>/dev/null
echo "--- container curl /api/tags ---"
docker exec "$CID" python3 -c "
import json, urllib.request
url='http://100.125.235.54:11434/api/tags'
try:
    with urllib.request.urlopen(url, timeout=12) as r:
        data=json.load(r)
    models=data.get('models') or []
    print('status=reachable http=200 count=%d' % len(models))
    for m in models:
        print('MODEL name=%s digest=%s size=%s' % (
            m.get('name'), (m.get('digest') or '')[:16], m.get('size')))
except Exception as exc:
    print('status=unreachable error=%s' % exc)
"
echo
EOS
}

echo "##### CT103 #####"
probe_host 192.168.4.62
echo "##### CT104 #####"
probe_host 192.168.4.63
