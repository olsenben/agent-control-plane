#!/usr/bin/env bash
# QA tip deploy verify smoke for 28292c0 (post wave3).
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:-28292c0}"
TIP="${TIP:0:7}"

echo "=== Tip pin + readyz CT103 ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
HEAD=\$(git rev-parse --short=7 HEAD)
echo "CT103_HEAD=\$HEAD expect=$TIP"
case "\$HEAD" in
  $TIP*) ;;
  *) echo TIP_MISMATCH; exit 1 ;;
esac
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:8080/readyz >/tmp/readyz.out; then
    echo READYZ_OK
    head -c 200 /tmp/readyz.out; echo
    break
  fi
  echo "readyz wait \$i"; sleep 3
done
curl -sf http://127.0.0.1:8080/readyz >/dev/null

# Observatory auth: missing → 401
CODE=\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/observe/repos/ai-sdlc-lab/demo-app || true)
echo "OBSERVE_NO_AUTH_HTTP=\$CODE"
case "\$CODE" in
  401|403) echo OBSERVE_AUTH_GATE_OK ;;
  *) echo "OBSERVE_AUTH_UNEXPECTED \$CODE"; exit 1 ;;
esac

# Eval export smoke (in-container)
cat > /tmp/qa_v6_smoke.py <<'PY'
from pathlib import Path
import tempfile
from agent_control.eval_export import export_eval_bundle, verify_eval_bundle_sha256
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_control.gitea_client import GiteaClient
from agent_control.observe.comment_projection import _reconcile_patch_applied
from agent_shared.models.agent_session import AgentSession, SessionStatus

assert hasattr(GiteaClient, "get_issue_comment")
assert callable(_reconcile_patch_applied)

root = Path(tempfile.mkdtemp())
project = "ai-sdlc-lab/demo-app"
run_id = "run-qa-v6-smoke"
session = AgentSession(
    session_id="sess-qa-v6-smoke",
    project=project,
    repo="demo-app",
    subject_kind="issue",
    subject_number=1,
    command_kind="plan",
    status=SessionStatus.QUEUED,
    run_ids=[run_id],
    correlation_id="corr-qa",
    trace_id="tr-qa",
    input_state_sha="a"*64,
    head_sha="b"*40,
    risk_level="risk1",
    invoked_by="smoke",
    created_at="2026-07-21T00:00:00+00:00",
    updated_at="2026-07-21T00:00:00+00:00",
)
persist_session_with_run_index(root, session)
append_control_decision(
    root,
    project=project,
    kind="other",
    summary="qa smoke",
    session_id=session.session_id,
    run_id=run_id,
    trace_id=session.trace_id,
)
bundle, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root/"out")
assert verify_eval_bundle_sha256(bundle)
assert bundle.production_memory_touched is False
print("QA_V6_SMOKE_OK", bundle.eval_bundle_sha256[:12])
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/qa_v6_smoke.py "\$CID":/tmp/qa_v6_smoke.py
docker compose exec -T control-plane python /tmp/qa_v6_smoke.py </dev/null

docker compose ps --format 'table {{.Name}}\t{{.Status}}' | head -10
EOS

echo "=== Tip pin CT104 ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" deploy@192.168.4.63 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
# Finish CT104 deploy if tip not yet pulled
HEAD=\$(git rev-parse --short=7 HEAD || echo none)
echo "CT104_HEAD_BEFORE=\$HEAD"
if [[ "\$HEAD" != $TIP* ]]; then
  bash scripts/deploy-git-pull.sh
  if grep -q '^MODEL_ROUTING_POLICY=' .env; then
    sed -i 's/^MODEL_ROUTING_POLICY=.*/MODEL_ROUTING_POLICY=fake/' .env
  else
    echo 'MODEL_ROUTING_POLICY=fake' >> .env
  fi
  docker compose -f docker-compose.ct104.yml build worker-rlm-root worker-report worker-ci-repair
  docker compose -f docker-compose.ct104.yml up -d worker-rlm-root worker-report worker-ci-repair
fi
HEAD=\$(git rev-parse --short=7 HEAD)
echo "CT104_HEAD=\$HEAD expect=$TIP"
case "\$HEAD" in
  $TIP*) ;;
  *) echo TIP_MISMATCH; exit 1 ;;
esac
# No write token on CT104
if grep -E 'GITEA_.*TOKEN|GITEA_WRITE' .env 2>/dev/null | grep -v '^#' | grep -qi write; then
  echo CT104_WRITE_TOKEN_PRESENT; exit 1
fi
echo CT104_NO_WRITE_TOKEN_OK
docker compose -f docker-compose.ct104.yml ps --format 'table {{.Name}}\t{{.Status}}' | head -10
EOS

echo "DEPLOY_VERIFY_QA_V6_PASS tip=$TIP"
