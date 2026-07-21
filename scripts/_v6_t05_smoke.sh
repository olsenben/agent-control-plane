#!/usr/bin/env bash
# V6 T05 deploy smoke on CT103 — authorization predicates + trailers.
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

cat > /tmp/v6_t05_smoke.py <<'PY'
from agent_shared.models.authorization_decision import evaluate_authorization
from agent_workers.publish.formatters import build_commit_message
from agent_shared.models.approval import FixAuthorizationBinding

plan = evaluate_authorization(
    command_kind="plan",
    project="demo/demo-app",
    invoker_login="reader",
    invoker_can_read=True,
    invoker_is_approver=False,
    approver_login=None,
    acting_identity="agent-bot",
    bot_can_write=False,
    policy_permits=True,
)
assert plan.decision == "allow", plan

deny_approve = evaluate_authorization(
    command_kind="approve",
    project="demo/demo-app",
    invoker_login="reader",
    invoker_can_read=True,
    invoker_is_approver=False,
    approver_login="reader",
    acting_identity="agent-bot",
    bot_can_write=True,
    policy_permits=True,
    require_approver=True,
)
assert deny_approve.decision == "deny", deny_approve

drift = evaluate_authorization(
    command_kind="publish",
    project="demo/demo-app",
    invoker_login="reader",
    invoker_can_read=True,
    invoker_is_approver=False,
    approver_login="owner",
    acting_identity="agent-bot",
    bot_can_write=True,
    policy_permits=True,
    approval_valid=False,
    approval_reason="source_sha_drift",
    require_approver=True,
    require_bot_write=True,
    approver_is_authority=True,
)
assert drift.decision == "deny", drift

binding = FixAuthorizationBinding(
    approval_id="a",
    approval_target_id="t",
    plan_run_id="run-p",
    plan_hash="h",
    blast_radius_hash="b",
    allowed_files=["x.py"],
)
msg = build_commit_message(
    run_id="run-1",
    binding=binding,
    approved_base_sha="abc",
    invoked_by="alice",
    session_id="sess-1",
    approved_by="owner",
)
assert "Invoked-By: alice" in msg
assert "Agent-Run: run-1" in msg
assert "Agent-Session: sess-1" in msg
print("V6_T05_SMOKE_OK")
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/v6_t05_smoke.py "\$CID":/tmp/v6_t05_smoke.py
docker compose exec -T control-plane python /tmp/v6_t05_smoke.py </dev/null
EOS

echo DEPLOY_SMOKE_V6_T05_PASS tip=$TIP
