#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?short tip}"
TIP="${TIP:0:7}"

ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
HEAD=\$(git rev-parse --short=7 HEAD)
echo "CT103_HEAD=\$HEAD expect=$TIP"
case "\$HEAD" in
  $TIP*) ;;
  *) echo TIP_MISMATCH; exit 1 ;;
esac
for i in 1 2 3 4 5 6 7 8; do
  curl -sf http://127.0.0.1:8080/readyz >/dev/null && break
  sleep 2
done
cat > /tmp/v7_t03_smoke.py <<'PY'
from pathlib import Path
import tempfile
from agent_control.bakeoff_metrics import METRIC_FIELDS, build_metrics_for_bundle_file
from agent_control.bakeoff_profiles import run_profile_against_bundle
from agent_control.eval_export import export_eval_bundle
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus

root = Path(tempfile.mkdtemp())
project = "ai-sdlc-lab/demo-app"
run_id = "run-v7t03-smoke"
session = AgentSession(
    session_id="sess-v7t03-smoke",
    project=project,
    repo="demo-app",
    subject_kind="issue",
    subject_number=1,
    command_kind="fix",
    status=SessionStatus.QUEUED,
    run_ids=[run_id],
    correlation_id="c",
    trace_id="t",
    input_state_sha="a"*64,
    head_sha="b"*40,
    risk_level="risk2",
    invoked_by="smoke",
    created_at="2026-07-21T00:00:00+00:00",
    updated_at="2026-07-21T00:00:00+00:00",
)
persist_session_with_run_index(root, session)
append_control_decision(root, project=project, kind="other", summary="repair iter 1", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
append_control_decision(root, project=project, kind="model_fallback_selected", summary="fallback", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
append_control_decision(root, project=project, kind="policy_denied", summary="denied", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
append_control_decision(root, project=project, kind="ci_verdict_accepted", summary="ct102 verified", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
_, bpath = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root/"exp")
metrics = build_metrics_for_bundle_file(bpath)
assert metrics["schema_version"] == "bakeoff_metrics.v1"
for f in METRIC_FIELDS:
    assert f in metrics
assert metrics["repair_iterations"] >= 1
assert metrics["fallback_count"] >= 1
assert metrics["policy_violations"] >= 1
assert metrics["ct102_verified_success"] is True
doc, _ = run_profile_against_bundle(bpath, "A", output_dir=root/"out")
assert doc["metrics"]["schema_version"] == "bakeoff_metrics.v1"
print("V7_T03_SMOKE_OK", "repair", metrics["repair_iterations"], "fallback", metrics["fallback_count"])
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/v7_t03_smoke.py "\$CID":/tmp/v7_t03_smoke.py
docker compose exec -T control-plane python /tmp/v7_t03_smoke.py </dev/null
EOS

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 \
  "cd /opt/ai-sdlc-lab/agent-control-plane && echo CT104 \$(git rev-parse --short=7 HEAD)"
echo DEPLOY_SMOKE_V7_T03_PASS tip=$TIP
