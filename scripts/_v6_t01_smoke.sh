#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?short tip}"
TIP="${TIP:0:7}"

echo "=== wait tip $TIP on CT103+CT104 ==="
bash /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_wait_tip_57.sh "$TIP"

echo "=== CT103 /readyz ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'curl -sf http://127.0.0.1:8080/readyz | head -c 500; echo'

echo "=== CT103 V6 T01 smoke ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
cat > /tmp/v6_t01_smoke.py <<'PY'
from pathlib import Path
import os
import tempfile

os.environ["OTEL_SDK_DISABLED"] = "true"

from agent_control.session.lifecycle import begin_typed_session
from agent_control.observe.events import append_control_decision
from agent_control.observe.projection import build_observation_projection
from agent_shared.models.jobs import TriggerContext

root = Path(tempfile.mkdtemp())
project = "ai-sdlc-lab/demo-app"
run_id = "run-v6-t01-smoke"
session = begin_typed_session(
    root,
    project=project,
    command_kind="review",
    run_id=run_id,
    head_sha="deadbeef",
    trigger_context=TriggerContext(event_type="issue_comment", author="smoke", issue_number=1),
)
assert session.trace_id and len(session.trace_id) == 32, session.trace_id
append_control_decision(
    root,
    project=project,
    kind="policy_denied",
    summary="smoke decision",
    session_id=session.session_id,
    run_id=run_id,
    trace_id=session.trace_id,
)
doc = build_observation_projection(root, project=project, run_id=run_id)
assert doc.trace_id == session.trace_id
assert doc.max_sequence >= 2
print("V6_T01_SMOKE_OK", session.session_id, session.trace_id, doc.max_sequence)
PY
CID=$(docker compose ps -q control-plane)
docker cp /tmp/v6_t01_smoke.py "$CID":/tmp/v6_t01_smoke.py
docker compose exec -T control-plane python /tmp/v6_t01_smoke.py </dev/null
EOS

echo "=== CT104 no write token ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
if docker compose -f docker-compose.ct104.yml exec -T worker-rlm-root sh -c 'env' </dev/null 2>/dev/null | grep -Eiq 'GITEA_(BOT|AGENT)_TOKEN=.+'; then
  echo CT104_HAS_WRITE_TOKEN >&2
  exit 1
fi
echo CT104_NO_WRITE_TOKEN_OK
EOS

echo DEPLOY_SMOKE_V6_T01_PASS tip=$TIP
