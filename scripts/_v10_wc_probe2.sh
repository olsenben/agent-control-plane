#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
CID=$(docker compose ps -q control-plane)
echo "=== EGRESS / GATEWAY / POLICY ENV ==="
docker exec "$CID" printenv | grep -Ei '(REPO_EXTERNAL|GATEWAY|CODE_HANDLING|FALLBACK_ENABLED|ROUTING_POLICY|RECURSIVE)' | sed -E 's/(KEY|TOKEN|SECRET)=(.+)/\1=<redacted:set>/' | sort || echo "(none)"
echo "=== 2070 REACHABILITY FROM CONTAINER ==="
docker exec "$CID" python3 -c "
import httpx,json
r=httpx.get('http://100.125.235.54:11434/api/tags',timeout=8)
print('status',r.status_code)
print(json.dumps([m['name'] for m in r.json().get('models',[])],indent=0))
" </dev/null || echo "UNREACHABLE"
echo "=== RESOLVED SUMMARIZER ROUTE ==="
docker exec "$CID" python3 -c "
from agent_control.config import get_settings
from agent_control.model_router import resolve_role_primary
from agent_control.model_gateway import _candidate_endpoints, gateway_endpoint_for_role
s=get_settings()
print('repo_external_model_policy=', repr(getattr(s,'repo_external_model_policy','<missing>')))
print('model_fallback_enabled=', s.model_fallback_enabled)
print('gateway=', repr(getattr(s,'model_gateway_base_url','<missing>')))
print('gateway_endpoint_for_role=', gateway_endpoint_for_role('summarizer', s))
print('primary=', resolve_role_primary('summarizer', s).as_dict())
for proj in ('v10-wave-c-smoke','homelab/agent-control-plane'):
    print(proj, [(l, e.provider, e.model, e.base_url, leaves) for l,e,leaves in _candidate_endpoints('summarizer', project=proj, settings=s)])
" </dev/null
EOS
