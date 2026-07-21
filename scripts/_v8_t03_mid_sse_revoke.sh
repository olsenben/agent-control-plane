#!/usr/bin/env bash
# V8 T03 — live mid-SSE shared-token revoke on CT103 Observatory.
# Prefer rotating <AGENT_STATE_ROOT>/.observe_shared_token mid-stream (no restart).
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:-}"
EVIDENCE_DIR="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
HEAD=\$(git rev-parse --short=7 HEAD)
echo "CT103_HEAD=\$HEAD"
if [ -n "$TIP" ]; then
  case "\$HEAD" in
    ${TIP:0:7}*) ;;
    *) echo TIP_MISMATCH expect=${TIP:0:7}; exit 1 ;;
  esac
fi
for i in 1 2 3 4 5 6 7 8; do
  curl -sf http://127.0.0.1:8080/readyz >/dev/null && break
  sleep 2
done

# Seed a throwaway session + hot-reload token file inside the running container FS.
cat > /tmp/v8_t03_seed.py <<'PY'
import os
import time
from pathlib import Path

from agent_control.observe.auth import OBSERVE_SHARED_TOKEN_FILENAME
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus

root = Path(os.environ["AGENT_STATE_ROOT"])
project = "ai-sdlc-lab/demo-app"
run_id = "run-v8t03-live"
session = AgentSession(
    session_id="sess-v8t03-live",
    project=project,
    repo="demo-app",
    subject_kind="issue",
    subject_number=99903,
    command_kind="plan",
    status=SessionStatus.QUEUED,
    run_ids=[run_id],
    correlation_id="corr-v8t03-live",
    trace_id="tr-v8t03-live",
    input_state_sha="a" * 64,
    head_sha="b" * 40,
    policy_source_sha="c" * 40,
    risk_level="risk1",
    invoked_by="v8t03-live",
    created_at="2026-07-21T00:00:00+00:00",
    updated_at="2026-07-21T00:00:00+00:00",
)
persist_session_with_run_index(root, session)
append_control_decision(
    root,
    project=project,
    kind="other",
    summary="v8-t03-live-seed",
    session_id=session.session_id,
    run_id=run_id,
    trace_id=session.trace_id,
)
token_path = root / OBSERVE_SHARED_TOKEN_FILENAME
token_v1 = f"v8t03-live-{int(time.time())}-a"
token_path.write_text(token_v1 + "\n", encoding="utf-8")
print(f"SEED_OK run_id={run_id} token_path={token_path}")
print(f"TOKEN_V1={token_v1}")
PY
CID=\$(docker compose ps -q control-plane)
docker cp /tmp/v8_t03_seed.py "\$CID":/tmp/v8_t03_seed.py
SEED_OUT=\$(docker compose exec -T control-plane python /tmp/v8_t03_seed.py </dev/null)
echo "\$SEED_OUT"
TOKEN_V1=\$(echo "\$SEED_OUT" | awk -F= '/^TOKEN_V1=/{print \$2}')
test -n "\$TOKEN_V1"

# Client: open SSE, after first data frame rotate token file, expect forbidden error.
cat > /tmp/v8_t03_client.py <<'PY'
import os
import sys
import time
import urllib.request
from pathlib import Path

token_v1 = os.environ["TOKEN_V1"]
root = Path(os.environ["AGENT_STATE_ROOT"])
token_path = root / ".observe_shared_token"
run_id = "run-v8t03-live"
project = "ai-sdlc-lab/demo-app"
url = f"http://127.0.0.1:8080/api/observe/sessions/{run_id}/stream?project={project}"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token_v1}"})

token_v2 = token_v1.rsplit("-", 1)[0] + "-b-rotated"
rotated = False
saw_data = False
saw_error = False
buf = ""
deadline = time.time() + 25

with urllib.request.urlopen(req, timeout=30) as resp:
    assert resp.status == 200, resp.status
    while time.time() < deadline:
        chunk = resp.read(256)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        if (not saw_data) and "data:" in buf:
            saw_data = True
        if saw_data and not rotated:
            token_path.write_text(token_v2 + "\n", encoding="utf-8")
            rotated = True
            print(f"ROTATED path={token_path}")
        if "event: error" in buf and "forbidden" in buf:
            saw_error = True
            break
        if "event: end" in buf and rotated:
            # Ended without unauthorized — fail
            break

print(f"SAW_DATA={saw_data} ROTATED={rotated} SAW_ERROR={saw_error}")
# Cleanup hot-reload file so we do not leave a live shared token behind.
try:
    token_path.unlink(missing_ok=True)
    print("TOKEN_FILE_REMOVED")
except OSError as exc:
    print(f"TOKEN_FILE_CLEANUP_WARN {exc}")

if not (saw_data and rotated and saw_error):
    print("BUF_TAIL=")
    print(buf[-800:])
    sys.exit(1)
print("V8_T03_MID_SSE_REVOKE_OK")
PY

# Run client inside container (loopback to control-plane).
docker cp /tmp/v8_t03_client.py "\$CID":/tmp/v8_t03_client.py
# AGENT_STATE_ROOT already set in container; pass TOKEN_V1
PROOF=\$(docker compose exec -T -e TOKEN_V1="\$TOKEN_V1" control-plane python /tmp/v8_t03_client.py </dev/null)
echo "\$PROOF"
echo "\$PROOF" | grep -q V8_T03_MID_SSE_REVOKE_OK
EOS

echo "DEPLOY_SMOKE_V8_T03_PASS tip=${TIP:-unknown}"
if [ -n "$EVIDENCE_DIR" ]; then
  mkdir -p "$EVIDENCE_DIR"
  echo "V8_T03_MID_SSE_REVOKE_OK tip=${TIP:-unknown} $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$EVIDENCE_DIR/smoke.txt"
fi
