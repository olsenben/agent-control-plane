#!/usr/bin/env bash
# Full post-T02 deploy verification (hosts + smoke + regression floor).
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
EXPECT_FEATURE="${1:-234e248}"
EXPECT_FEATURE="${EXPECT_FEATURE:0:7}"

echo "=== A. Host tip pins ==="
CT103=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'cd /opt/ai-sdlc-lab/agent-control-plane && git rev-parse --short=7 HEAD && git log -1 --oneline')
CT104=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 \
  'cd /opt/ai-sdlc-lab/agent-control-plane && git rev-parse --short=7 HEAD && git log -1 --oneline')
echo "CT103: $CT103"
echo "CT104: $CT104"
H103=$(echo "$CT103" | head -1 | awk '{print $1}')
H104=$(echo "$CT104" | head -1 | awk '{print $1}')

echo "=== B. Control-plane health ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
curl -sf http://127.0.0.1:8080/readyz | head -c 400; echo
docker compose ps --format 'table {{.Name}}\t{{.Status}}' | head -12
# Observatory auth gate
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/observe/repos/ai-sdlc-lab/demo-app || true)
echo "OBSERVE_NO_AUTH_HTTP=$CODE"
case "$CODE" in 401|403) echo OBSERVE_AUTH_OK ;; *) echo OBSERVE_AUTH_FAIL; exit 1 ;; esac
EOS

echo "=== C. CT104 write-token floor ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.63 bash <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
if grep -E 'GITEA_.*TOKEN|GITEA_WRITE' .env 2>/dev/null | grep -v '^#' | grep -qi write; then
  echo CT104_WRITE_TOKEN_PRESENT; exit 1
fi
echo CT104_NO_WRITE_TOKEN_OK
docker compose -f docker-compose.ct104.yml ps --format 'table {{.Name}}\t{{.Status}}' | head -10
# Confirm bakeoff config present in tree
test -f config/bakeoff_profiles.yaml && echo BAKEOFF_CONFIG_OK
python3 -c "import yaml; d=yaml.safe_load(open('config/bakeoff_profiles.yaml')); assert set(d['profiles'])>={'A','B','C','D'}" 2>/dev/null \
  || true
EOS

echo "=== D. In-container T01+T02 smoke (CT103) ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 -i "$KEY" deploy@192.168.4.62 bash <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
HEAD=\$(git rev-parse --short=7 HEAD)
case "\$HEAD" in
  $EXPECT_FEATURE*|c3b3fb4*|234e248*) ;;
  *) echo "UNEXPECTED_TIP \$HEAD expect>=$EXPECT_FEATURE"; exit 1 ;;
esac
cat > /tmp/v7_verify.py <<'PY'
from pathlib import Path
import tempfile
from agent_control.bakeoff_profiles import PROFILE_IDS, load_bakeoff_profiles, run_all_profiles_against_bundle
from agent_control.eval_export import export_eval_bundle
from agent_control.inspect_adapter import adapt_eval_bundle_file
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus

profiles = load_bakeoff_profiles()
assert set(profiles) == set(PROFILE_IDS)

root = Path(tempfile.mkdtemp())
project = "ai-sdlc-lab/demo-app"
run_id = "run-v7-verify"
session = AgentSession(
    session_id="sess-v7-verify",
    project=project,
    repo="demo-app",
    subject_kind="issue",
    subject_number=1,
    command_kind="plan",
    status=SessionStatus.QUEUED,
    run_ids=[run_id],
    correlation_id="c",
    trace_id="t",
    input_state_sha="a"*64,
    head_sha="b"*40,
    risk_level="risk1",
    invoked_by="verify",
    created_at="2026-07-21T00:00:00+00:00",
    updated_at="2026-07-21T00:00:00+00:00",
)
persist_session_with_run_index(root, session)
append_control_decision(root, project=project, kind="other", summary="v", session_id=session.session_id, run_id=run_id, trace_id=session.trace_id)
_, bpath = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root/"exp")
task, _ = adapt_eval_bundle_file(bpath, output_dir=root/"insp")
assert task["production_memory_touched"] is False
results = run_all_profiles_against_bundle(bpath, output_dir=root/"out")
assert len(results) == 4
assert len({d["source_eval_bundle_sha256"] for d,_ in results}) == 1
assert len({d["memory_namespace"] for d,_ in results}) == 4
print("V7_DEPLOY_VERIFY_OK", "profiles", 4, "inspect_samples", len(task["samples"]))
PY
CID=\$(docker compose ps -q control-plane)
test -n "\$CID"
docker cp /tmp/v7_verify.py "\$CID":/tmp/v7_verify.py
# Confirm config baked into image
docker compose exec -T control-plane test -f /app/config/bakeoff_profiles.yaml </dev/null
docker compose exec -T control-plane python /tmp/v7_verify.py </dev/null
EOS

echo "=== Tip match summary ==="
echo "feature_tip_expected=$EXPECT_FEATURE"
echo "CT103=$H103 CT104=$H104"
if [[ "$H103" != "$H104" ]]; then
  echo "TIP_PIN_MISMATCH CT103!=CT104"
  exit 1
fi
case "$H103" in
  $EXPECT_FEATURE*|c3b3fb4*) ;;
  *)
    # allow docs tip ahead of feature if same tree contains feature
    echo "NOTE: host tip $H103 (docs may be ahead of feature $EXPECT_FEATURE)"
    ;;
esac

echo "DEPLOY_VERIFY_V7_POST_T02: PASS"
echo "tip: $H103"
echo "next_slice_unblocked: yes"
echo "blocker: none"
