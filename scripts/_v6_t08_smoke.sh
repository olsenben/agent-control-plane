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

cat > /tmp/v6_t08_smoke.py <<'PY'
from pathlib import Path
import tempfile
from agent_control.eval_export import export_eval_bundle, verify_eval_bundle_sha256
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus

root = Path(tempfile.mkdtemp())
project = "ai-sdlc-lab/demo-app"
run_id = "run-t08smoke"
session = AgentSession(
    session_id="sess-t08smoke",
    project=project,
    repo="demo-app",
    subject_kind="issue",
    subject_number=1,
    command_kind="plan",
    status=SessionStatus.QUEUED,
    run_ids=[run_id],
    correlation_id="corr-t08",
    trace_id="tr-t08",
    input_state_sha="a"*64,
    head_sha="b"*40,
    risk_level="risk1",
    invoked_by="smoke",
    created_at="2026-07-21T00:00:00+00:00",
    updated_at="2026-07-21T00:00:00+00:00",
)
persist_session_with_run_index(root, session)
append_control_decision(root, project=project, kind="other", summary="smoke", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
bundle, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root/"out")
assert verify_eval_bundle_sha256(bundle)
assert bundle.production_memory_touched is False
assert path.is_file()
print("V6_T08_SMOKE_OK", bundle.eval_bundle_sha256[:12])
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/v6_t08_smoke.py "\$CID":/tmp/v6_t08_smoke.py
docker compose exec -T control-plane python /tmp/v6_t08_smoke.py </dev/null
EOS
echo DEPLOY_SMOKE_V6_T08_PASS tip=$TIP
