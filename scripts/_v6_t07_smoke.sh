#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?short tip}"
TIP="${TIP:0:7}"

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
HEAD=\$(git rev-parse --short=7 HEAD)
echo "CT103_HEAD=\$HEAD expect=$TIP"
case "\$HEAD" in
  $TIP*) ;;
  *) echo "TIP_MISMATCH"; exit 1 ;;
esac

cat > /tmp/v6_t07_smoke.py <<'PY'
from agent_control.intent_parser import parse_command_intent
from agent_control.state_reducer import dispatch_for_comment_body
from agent_control.nl_intent import extract_agent_intent
from agent_control.invocation import begin_invocation, request_clarification
from pathlib import Path
import tempfile

i, d, k = dispatch_for_comment_body("/agent review")
assert i.activated and i.kind == "review" and d and k == "review"

i2 = parse_command_intent("@agent explain why CI fails")
assert i2.activated and i2.kind == "explain" and i2.activation == "@agent"

i3, d3, _ = dispatch_for_comment_body("explain why CI fails")
assert not i3.activated and not d3

root = Path(tempfile.mkdtemp())
ai = extract_agent_intent("@agent do the thing")
rec = begin_invocation(root, project="ai-sdlc-lab/demo-app", raw_text="@agent do the thing", intent=ai)
assert request_clarification(root, rec).status == "clarification_requested"
print("V6_T07_SMOKE_OK")
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/v6_t07_smoke.py "\$CID":/tmp/v6_t07_smoke.py
docker compose exec -T control-plane python /tmp/v6_t07_smoke.py </dev/null
EOS
echo DEPLOY_SMOKE_V6_T07_PASS tip=$TIP
