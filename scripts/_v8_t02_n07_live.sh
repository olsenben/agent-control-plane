#!/usr/bin/env bash
# V8 T02 / N07 live — add disposable collaborator, prove publish recheck allow,
# DELETE collaborator, prove authorization_denied on recheck.
#
# Requires: DISPOSABLE_APPROVER=<gitea login that already exists>
# Safe: never touches production approver olsenben as revoke target.
# Uses runtime Settings override inside the control-plane container only.
#
# Exit codes:
#   0  — N07_LIVE_PASS
#   2  — WaitingHuman (no disposable principal / cannot revoke)
#   1  — unexpected failure
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
PROJECT="${N07_PROJECT:-ai-sdlc-lab/demo-app}"
OWNER="${PROJECT%%/*}"
REPO="${PROJECT##*/}"
DISP="${DISPOSABLE_APPROVER:-}"
EVIDENCE_DIR="${N07_EVIDENCE_DIR:-docs/handoff/evidence}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "${REPO_ROOT}/${EVIDENCE_DIR}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_REL="${EVIDENCE_DIR}/v8-t02-n07-${STAMP}.txt"
EVIDENCE_LOCAL="${REPO_ROOT}/${EVIDENCE_REL}"

if [[ -z "$DISP" ]]; then
  {
    echo "N07_LIVE_STATUS=WaitingHuman"
    echo "N07_LIVE_REASON=DISPOSABLE_APPROVER unset"
    echo "N07_LIVE_PROJECT=${PROJECT}"
  } | tee "$EVIDENCE_LOCAL"
  echo "evidence=${EVIDENCE_REL}"
  exit 2
fi

if [[ "$DISP" == "olsenben" ]]; then
  {
    echo "N07_LIVE_STATUS=WaitingHuman"
    echo "N07_LIVE_REASON=refusing to revoke production approver olsenben"
  } | tee "$EVIDENCE_LOCAL"
  echo "evidence=${EVIDENCE_REL}"
  exit 2
fi

set +e
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  env OWNER="$OWNER" REPO="$REPO" DISP="$DISP" bash -s <<'EOS' | tee "$EVIDENCE_LOCAL"
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
set -a
# shellcheck disable=SC1091
source .env
set +a
BASE="${GITEA_BASE_URL%/}"
TOKEN="${GITEA_BOT_TOKEN:?missing}"
AUTH="Authorization: token ${TOKEN}"
PROJECT="${OWNER}/${REPO}"

echo "N07_LIVE_PROJECT=${PROJECT}"
echo "N07_LIVE_DISPOSABLE=${DISP}"
echo "N07_LIVE_TIP=$(git rev-parse --short=7 HEAD)"

code=$(curl -s -o /tmp/n07_before.json -w "%{http_code}" -H "$AUTH" \
  "${BASE}/api/v1/repos/${OWNER}/${REPO}/collaborators/${DISP}/permission")
echo "N07_LIVE_PERM_BEFORE_HTTP=${code}"
head -c 240 /tmp/n07_before.json; echo

code=$(curl -s -o /tmp/n07_put.json -w "%{http_code}" -X PUT -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"permission":"write"}' \
  "${BASE}/api/v1/repos/${OWNER}/${REPO}/collaborators/${DISP}")
echo "N07_LIVE_PUT_HTTP=${code}"
head -c 300 /tmp/n07_put.json; echo

if [[ "$code" != "204" && "$code" != "200" ]]; then
  echo "N07_LIVE_STATUS=WaitingHuman"
  echo "N07_LIVE_REASON=cannot_add_collaborator http=${code} (user missing or insufficient admin)"
  exit 2
fi

cat > /tmp/n07_recheck.py <<'PY'
import json, os, sys
from pathlib import Path

from agent_control.authorization import (
    append_authorization_decision,
    recheck_publish_authorization,
)
from agent_control.config import Settings

disp = os.environ["N07_DISP"]
project = os.environ["N07_PROJECT"]
phase = os.environ["N07_PHASE"]
invoker = (os.environ.get("N07_INVOKER") or "").strip() or disp
settings = Settings(
    GITEA_BOT_TOKEN=os.environ["GITEA_BOT_TOKEN"],
    GITEA_BASE_URL=os.environ["GITEA_BASE_URL"],
    GITEA_APPROVER_LOGINS=disp,
    GITEA_ACTING_IDENTITY=os.environ.get("GITEA_ACTING_IDENTITY") or "agent-bot",
)
auth = recheck_publish_authorization(
    project=project,
    invoker_login=invoker,
    approver_login=disp,
    source_sha="n07deadbeef",
    approval_valid=True,
    run_id=f"run-n07-{phase}",
    session_id=f"sess-n07-{phase}",
    settings=settings,
)
state = Path(os.environ.get("AGENT_STATE_ROOT") or "/data/agent-state")
path, created = append_authorization_decision(state, auth)
out = {
    "phase": phase,
    "decision": auth.decision,
    "approver_allowed": auth.approver_check.allowed,
    "approver_reason": auth.approver_check.reason,
    "invoker_allowed": auth.invoker_check.allowed,
    "acting_allowed": auth.acting_identity_check.allowed,
    "event_path": str(path),
    "event_created": created,
}
print(json.dumps(out))
sys.exit(0 if auth.decision == os.environ["N07_EXPECT"] else 3)
PY

export N07_DISP="$DISP" N07_PROJECT="$PROJECT"
export N07_INVOKER="${GITEA_APPROVER_LOGINS%%,*}"
CID=$(docker compose ps -q control-plane)
docker cp /tmp/n07_recheck.py "$CID":/tmp/n07_recheck.py

export N07_PHASE=before N07_EXPECT=allow
set +e
before=$(docker compose exec -T \
  -e N07_DISP -e N07_PROJECT -e N07_PHASE -e N07_EXPECT -e N07_INVOKER \
  -e GITEA_BOT_TOKEN -e GITEA_BASE_URL -e GITEA_ACTING_IDENTITY -e AGENT_STATE_ROOT \
  control-plane python /tmp/n07_recheck.py </dev/null)
rc_before=$?
set -e
echo "N07_LIVE_BEFORE=${before}"
echo "N07_LIVE_BEFORE_RC=${rc_before}"

code=$(curl -s -o /tmp/n07_del.json -w "%{http_code}" -X DELETE -H "$AUTH" \
  "${BASE}/api/v1/repos/${OWNER}/${REPO}/collaborators/${DISP}")
echo "N07_LIVE_DELETE_HTTP=${code}"
head -c 200 /tmp/n07_del.json; echo

if [[ "$code" != "204" && "$code" != "200" ]]; then
  echo "N07_LIVE_STATUS=WaitingHuman"
  echo "N07_LIVE_REASON=cannot_delete_collaborator http=${code}"
  exit 2
fi

code=$(curl -s -o /tmp/n07_after.json -w "%{http_code}" -H "$AUTH" \
  "${BASE}/api/v1/repos/${OWNER}/${REPO}/collaborators/${DISP}/permission")
echo "N07_LIVE_PERM_AFTER_HTTP=${code}"

export N07_PHASE=after N07_EXPECT=deny
set +e
after=$(docker compose exec -T \
  -e N07_DISP -e N07_PROJECT -e N07_PHASE -e N07_EXPECT -e N07_INVOKER \
  -e GITEA_BOT_TOKEN -e GITEA_BASE_URL -e GITEA_ACTING_IDENTITY -e AGENT_STATE_ROOT \
  control-plane python /tmp/n07_recheck.py </dev/null)
rc_after=$?
set -e
echo "N07_LIVE_AFTER=${after}"
echo "N07_LIVE_AFTER_RC=${rc_after}"

if [[ "$rc_before" -eq 0 && "$rc_after" -eq 0 ]]; then
  echo "N07_LIVE_STATUS=Done"
  echo "N07_LIVE_VERDICT=PASS"
  exit 0
fi
echo "N07_LIVE_STATUS=Blocked"
echo "N07_LIVE_VERDICT=FAIL before_rc=${rc_before} after_rc=${rc_after}"
exit 1
EOS
rc=${PIPESTATUS[0]}
set -e
echo "evidence=${EVIDENCE_REL}"
exit "$rc"
