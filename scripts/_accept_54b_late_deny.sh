#!/usr/bin/env bash
# 5.4b homelab acceptance B: broker attestation deny -> session_blocked.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Tips ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$KEY" deploy@192.168.4.62 \
  'cd /opt/ai-sdlc-lab/agent-control-plane && git log -1 --oneline && test -f src/agent_control/session/reasons.py && echo HAS_54B'

echo "=== Copy acceptance script to CT103 ==="
scp -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" \
  "$SCRIPT_DIR/_accept_54b_late_deny.py" \
  deploy@192.168.4.62:/tmp/_accept_54b_late_deny.py

echo "=== Run late-deny broker attestation gate ==="
OUT=$(ssh -o BatchMode=yes -o ConnectTimeout=60 -i "$KEY" deploy@192.168.4.62 bash <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
CID=$(docker compose ps -q control-plane)
docker cp /tmp/_accept_54b_late_deny.py "${CID}:/tmp/_accept_54b_late_deny.py"
docker compose exec -T control-plane python3 /tmp/_accept_54b_late_deny.py </dev/null
EOS
)
echo "$OUT"

SID=$(echo "$OUT" | awk '/^POSITIVE_OK/ {print $2}')
RUN_ID=$(echo "$OUT" | awk '/^POSITIVE_OK/ {print $3}')
if [[ -z "$SID" || -z "$RUN_ID" ]]; then
  echo "NO_POSITIVE_OK" >&2
  exit 1
fi

echo "=== Ledger checks for $SID ($RUN_ID) ==="
ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash <<EOS
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
repo = "ai-sdlc-lab/demo-app"
owner, name = repo.split("/", 1)
root = Path("/mnt/agent-state/projects") / owner / name
sid = "${SID}"
run_id = "${RUN_ID}"
s = json.loads((root / "sessions" / f"{sid}.json").read_text())
assert s["status"] == "blocked", s["status"]
assert s["terminal_reason_code"] == "sandbox_unavailable", s["terminal_reason_code"]
domain = (s.get("terminal_reason") or "")
if isinstance(domain, str) and domain.strip().startswith("{"):
    domain = json.loads(domain).get("domain_reasons") or []
elif not isinstance(domain, list):
    domain = []
assert any("attestation" in str(c).lower() for c in domain), domain
events = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "events").rglob("*.json"))]
blocked = [e for e in events if e.get("type") == "agent.session_blocked" and (e.get("payload") or {}).get("session_id") == sid]
finished = [e for e in events if e.get("type") == "agent.session_finished" and (e.get("payload") or {}).get("session_id") == sid]
failed = [e for e in events if e.get("type") == "agent.session_failed" and (e.get("payload") or {}).get("session_id") == sid]
assert len(blocked) == 1, blocked
assert len(finished) == 0, finished
assert len(failed) == 0, failed
# No remote publish result for this run (broker rejected before push)
pub = root / "publish-results" / run_id
assert not any(pub.rglob("remote_publish_result.json")) if pub.exists() else True
print("LEDGER_OK", sid, run_id)
PY
EOS

echo "=== Done ==="
echo "SESSION_ID=$SID"
echo "RUN_ID=$RUN_ID"
