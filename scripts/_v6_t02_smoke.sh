#!/usr/bin/env bash
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?tip}"
TIP="${TIP:0:7}"
bash /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_wait_tip_57.sh "$TIP"
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose exec -T control-plane python -c "
from agent_control.observe.comment_projection import _should_apply_update, display_status_from_session
from agent_shared.models.agent_session import AgentSession, SessionStatus
s = AgentSession(
    session_id='sess-smoke', project='ai-sdlc-lab/demo-app', repo='demo-app',
    subject_kind='issue', subject_number=1, command_kind='review',
    status=SessionStatus.QUEUED, run_ids=['run-smoke'], correlation_id='c',
    input_state_sha='a', head_sha='b', risk_level='risk_1', invoked_by='x',
    created_at='t', updated_at='t', last_rendered_event_sequence=2, last_rendered_status='waiting_for_ci',
)
assert not _should_apply_update(s, event_sequence=1, display_status='running')
print('V6_T02_SMOKE_OK')
" </dev/null
EOS
echo DEPLOY_SMOKE_V6_T02_PASS tip=$TIP
