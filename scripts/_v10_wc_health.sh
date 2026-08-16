#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
echo "##### CT103 #####"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set +e
cd /opt/ai-sdlc-lab/agent-control-plane
echo "TIP=$(git rev-parse HEAD)"
echo "--- /readyz (raw) ---"
curl -s -o /tmp/_readyz.json -w 'http_status=%{http_code}\n' http://127.0.0.1:8080/readyz
python3 -c "import json;d=json.load(open('/tmp/_readyz.json'));print('ready=',d.get('ready'));print(json.dumps({k:(v if not isinstance(v,dict) else {kk:vv for kk,vv in v.items() if kk in ('status','provider','model','base_url')}) for k,v in d.items()},indent=1)[:2000])" 2>/dev/null || head -c 800 /tmp/_readyz.json
echo
echo "--- /healthz ---"
curl -s -w ' http_status=%{http_code}\n' http://127.0.0.1:8080/healthz
echo "--- new Wave C symbols present in running container ---"
CID=$(docker compose ps -q control-plane)
docker exec "$CID" python3 -c "
from agent_control.recursive_context.model_client import endpoint_is_homelab, ControllerEgressRefused, ControllerTelemetry
from agent_shared.models.recursive_context import RecursiveContextResult
f=RecursiveContextResult.model_fields
print('gpu_seconds_default=', f['controller_gpu_seconds'].default)
print('has_local_only=', 'controller_local_only_enforced' in f)
print('has_model_id_source=', 'controller_model_id_source' in f)
print('cgnat_allowed=', endpoint_is_homelab('http://100.125.235.54:11434'))
print('openai_refused=', not endpoint_is_homelab('https://api.openai.com/v1'))
from agent_workers.rlm.completion import chat_completion
import inspect
print('model_reported_in_completion=', 'model_reported' in inspect.getsource(chat_completion))
print('V10_WC_DEPLOY_SYMBOLS_OK')
" </dev/null
EOS
echo "##### CT104 #####"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash -s <<'EOS'
set +e
cd /opt/ai-sdlc-lab/agent-control-plane
echo "TIP=$(git rev-parse HEAD)"
docker compose -f docker-compose.ct104.yml ps --format '{{.Service}} {{.State}}'
echo "--- credential floor detail (names only) ---"
docker compose -f docker-compose.ct104.yml ps -q | while read -r cid; do
  name=$(docker inspect -f '{{.Name}}' "$cid")
  hit=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$cid" \
    | grep -E '^(GITEA_[A-Z_]*(TOKEN|PASSWORD)|.*API_KEY|AGENT_STATE_TOKEN)=' \
    | awk -F= '{ if (length($2)>0) print $1"=<set:"length($2)"chars>"; else print $1"=<empty>" }')
  echo "container $name"
  echo "${hit:-  (none)}"
done
echo "--- new Wave C symbols in a CT104 worker ---"
WCID=$(docker compose -f docker-compose.ct104.yml ps -q worker-rlm-root)
docker exec "$WCID" python3 -c "
from agent_control.recursive_context.model_client import endpoint_is_homelab
print('cgnat_allowed=', endpoint_is_homelab('http://100.125.235.54:11434'))
print('openai_refused=', not endpoint_is_homelab('https://api.openai.com/v1'))
print('V10_WC_CT104_SYMBOLS_OK')
" </dev/null
EOS
