#!/usr/bin/env bash
# Remove CT104 external model keys. Never print secret values.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
HOST="deploy@192.168.4.63"
OUT="/mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/docs/evidence/v10-h1-sweci-repair/gate6-revoke-result.txt"

ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" "$HOST" 'bash -s' <<'EOS' > "$OUT"
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
ENV=.env
test -f "$ENV"
cp -a "$ENV" ".env.bak-gate6-$(date -u +%Y%m%dT%H%M%SZ)"
chmod 600 .env.bak-gate6-* 2>/dev/null || true

# Strip assignment lines only; do not echo file contents.
python3 - <<'PY'
from pathlib import Path
p = Path(".env")
text = p.read_text(encoding="utf-8")
drop = ("MODEL_2070_EXTERNAL_API_KEY=", "MODEL_3080_EXTERNAL_API_KEY=")
kept = []
removed = 0
for line in text.splitlines(keepends=True):
    stripped = line.lstrip()
    if stripped.startswith(drop):
        removed += 1
        continue
    kept.append(line)
p.write_text("".join(kept), encoding="utf-8")
print(f"HOST_LINES_REMOVED={removed}")
PY

host_present=0
if grep -E '^[[:space:]]*MODEL_2070_EXTERNAL_API_KEY=' "$ENV" >/dev/null 2>&1; then
  host_present=1
fi
if grep -E '^[[:space:]]*MODEL_3080_EXTERNAL_API_KEY=' "$ENV" >/dev/null 2>&1; then
  host_present=1
fi
if [ "$host_present" -eq 0 ]; then
  echo HOST_ENV_KEYS=ABSENT
else
  echo HOST_ENV_KEYS=PRESENT
  exit 1
fi

docker compose -f docker-compose.ct104.yml up -d --force-recreate --no-deps \
  worker-ci-repair worker-report worker-rlm-root

presence() {
  local svc="$1"
  local name
  name="$(docker compose -f docker-compose.ct104.yml exec -T "$svc" sh -c 'printenv | sed -n "s/=.*//p"' </dev/null | grep -E '^(MODEL_2070_EXTERNAL_API_KEY|MODEL_3080_EXTERNAL_API_KEY)$' || true)"
  if [ -n "$name" ]; then
    echo "CONTAINER service=$svc KEYS=PRESENT"
    return 1
  fi
  echo "CONTAINER service=$svc KEYS=ABSENT"
}

ok=0
presence worker-ci-repair || ok=1
presence worker-report || ok=1
presence worker-rlm-root || ok=1
docker compose -f docker-compose.ct104.yml ps --format '{{.Service}} {{.Name}} {{.Status}}'
exit "$ok"
EOS

echo "EXIT=$?"
