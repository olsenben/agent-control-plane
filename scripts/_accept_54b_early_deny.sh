#!/usr/bin/env bash
# 5.4b homelab acceptance A: /agent fix without approval -> session_blocked.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
REPO="${1:-ai-sdlc-lab/demo-app}"
ISSUE="${2:-2}"

eval "$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 \
  'cd /opt/ai-sdlc-lab/agent-control-plane; grep -E "^GITEA_BASE_URL=|^GITEA_BOT_TOKEN=" .env')"
BASE="${GITEA_BASE_URL%/}"
TOKEN="$GITEA_BOT_TOKEN"
OWNER="${REPO%/*}"
NAME="${REPO#*/}"

echo "=== Tips ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$KEY" deploy@192.168.4.62 \
  'cd /opt/ai-sdlc-lab/agent-control-plane && git log -1 --oneline && test -f src/agent_control/session/reasons.py && echo HAS_54B'

find_unapproved_plan() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash <<EOS
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
repo = "${REPO}"
issue = int("${ISSUE}")
owner, name = repo.split("/", 1)
root = Path("/mnt/agent-state/projects") / owner / name
approved = set()
ap_dir = root / "approvals"
if ap_dir.is_dir():
    for path in ap_dir.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if row.get("issue_id") == issue and row.get("status") in {"approved", "reserved", "claimed"}:
            approved.add(str(row.get("approval_target_id") or ""))
alias = ""
for path in sorted((root / "events").rglob("*.json")):
    try:
        e = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        continue
    if e.get("type") != "agent.run_completed":
        continue
    payload = e.get("payload") or {}
    if payload.get("command_kind") != "plan" or int(payload.get("issue_id") or 0) != issue:
        continue
    target = str(payload.get("approval_target_id") or "")
    if target and target in approved:
        continue
    if payload.get("plan_alias"):
        alias = payload["plan_alias"]
if alias:
    print(alias)
PY
EOS
}

TARGET="$(find_unapproved_plan || true)"
if [[ -z "$TARGET" ]]; then
  PLAN_MARKER="5.4b-plan-seed-$(date -u +%Y%m%dT%H%M%SZ)"
  echo "=== Seed /agent plan on $REPO#$ISSUE ($PLAN_MARKER) ==="
  curl -sf -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"body\":\"/agent plan\\n\\n($PLAN_MARKER)\"}" \
    "$BASE/api/v1/repos/$OWNER/$NAME/issues/$ISSUE/comments" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("plan_comment_id", d.get("id"))'

  echo "=== Poll for finished plan session on issue $ISSUE ==="
  for i in $(seq 1 48); do
    TARGET="$(find_unapproved_plan || true)"
    echo "[$i] plan_alias=${TARGET:-pending}"
    if [[ -n "$TARGET" ]]; then
      break
    fi
    sleep 5
  done
fi

if [[ -z "$TARGET" ]]; then
  echo "NO_PLAN_ALIAS" >&2
  exit 1
fi

MARKER="5.4b-early-deny-$(date -u +%Y%m%dT%H%M%SZ)"
echo "=== Post /agent fix $TARGET ($MARKER) on $REPO#$ISSUE (no approve) ==="
curl -sf -X POST \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"body\":\"/agent fix $TARGET\\n\\n($MARKER)\"}" \
  "$BASE/api/v1/repos/$OWNER/$NAME/issues/$ISSUE/comments" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("comment_id", d.get("id"))'

echo "=== Poll for blocked session (human_approval_required) ==="
SID=""
REASON=""
for i in $(seq 1 24); do
  out=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
docker compose exec -T control-plane agentctl session list --repo ${REPO} --command-kind fix --json </dev/null 2>/dev/null || true
EOS
)
  cand=$(echo "$out" | python3 -c '
import json,sys
raw=sys.stdin.read()
start=raw.find("["); end=raw.rfind("]")
if start<0:
  print(""); raise SystemExit(0)
items=json.loads(raw[start:end+1])
blk=[s for s in items if s.get("status")=="blocked" and s.get("terminal_reason_code")=="human_approval_required"]
if blk:
  s=blk[-1]
  print(s["session_id"]+"|"+s.get("terminal_reason_code","")+"|"+s["run_ids"][0])
' || true)
  echo "[$i] $cand"
  if [[ -n "$cand" ]]; then
    SID="${cand%%|*}"
    REASON="${cand#*|}"; REASON="${REASON%%|*}"
    break
  fi
  sleep 3
done

if [[ -z "$SID" ]]; then
  echo "NO_BLOCKED_SESSION" >&2
  exit 1
fi

echo "=== Ledger checks for $SID ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash <<EOS
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
repo = "${REPO}"
owner, name = repo.split("/", 1)
root = Path("/mnt/agent-state/projects") / owner / name
sid = "${SID}"
s = json.loads((root / "sessions" / f"{sid}.json").read_text())
assert s["status"] == "blocked", s["status"]
assert s["terminal_reason_code"] == "human_approval_required", s["terminal_reason_code"]
events = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "events").rglob("*.json"))]
started = [e for e in events if e.get("type") == "agent.session_started" and (e.get("payload") or {}).get("session_id") == sid]
resolved = [e for e in events if e.get("type") == "agent.subject_context_resolved" and (e.get("payload") or {}).get("session_id") == sid]
blocked = [e for e in events if e.get("type") == "agent.session_blocked" and (e.get("payload") or {}).get("session_id") == sid]
finished = [e for e in events if e.get("type") == "agent.session_finished" and (e.get("payload") or {}).get("session_id") == sid]
failed = [e for e in events if e.get("type") == "agent.session_failed" and (e.get("payload") or {}).get("session_id") == sid]
worker = [e for e in events if e.get("type") == "agent.session_worker_event" and (e.get("payload") or {}).get("session_id") == sid]
run_done = [e for e in events if e.get("type") == "agent.run_completed" and (e.get("payload") or {}).get("session_id") == sid]
assert len(started) == 1, started
assert len(resolved) == 1, resolved
assert len(blocked) == 1, blocked
assert len(finished) == 0, finished
assert len(failed) == 0, failed
assert len(worker) == 0, worker
assert len(run_done) == 0, run_done
print("POSITIVE_OK", sid, s["terminal_reason_code"])
PY
EOS

echo "=== Done ==="
