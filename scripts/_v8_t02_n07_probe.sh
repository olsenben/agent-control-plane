#!/usr/bin/env bash
# V8 T02 / N07 — capability probe (CT103 bot token, demo-app admin, revoke API).
# Does not mutate production approvers. Exit 0 always; prints N07_PROBE_* lines.
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
PROJECT="${N07_PROJECT:-ai-sdlc-lab/demo-app}"
OWNER="${PROJECT%%/*}"
REPO="${PROJECT##*/}"

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
set -a
# shellcheck disable=SC1091
source .env
set +a
BASE="\${GITEA_BASE_URL%/}"
TOKEN="\${GITEA_BOT_TOKEN:?missing}"
AUTH="Authorization: token \${TOKEN}"
OWNER="$OWNER"
REPO="$REPO"
APPROVER="\${GITEA_APPROVER_LOGINS%%,*}"
DISP="\${DISPOSABLE_APPROVER:-}"

echo "N07_PROBE_BASE=\${BASE}"
echo "N07_PROBE_PROJECT=\${OWNER}/\${REPO}"
echo "N07_PROBE_CONFIGURED_APPROVER=\${APPROVER}"

code=\$(curl -s -o /tmp/n07_repo.json -w "%{http_code}" -H "\$AUTH" \
  "\${BASE}/api/v1/repos/\${OWNER}/\${REPO}")
echo "N07_PROBE_REPO_HTTP=\${code}"
python3 - <<'PY'
import json
r=json.load(open("/tmp/n07_repo.json"))
p=r.get("permissions") or {}
print("N07_PROBE_BOT_ADMIN="+str(bool(p.get("admin"))).lower())
print("N07_PROBE_BOT_PUSH="+str(bool(p.get("push"))).lower())
PY

code=\$(curl -s -o /tmp/n07_collabs.json -w "%{http_code}" -H "\$AUTH" \
  "\${BASE}/api/v1/repos/\${OWNER}/\${REPO}/collaborators")
echo "N07_PROBE_COLLABS_HTTP=\${code}"
python3 - <<'PY'
import json
try:
    data=json.load(open("/tmp/n07_collabs.json"))
except Exception:
    data=[]
if isinstance(data, list):
    print("N07_PROBE_COLLAB_COUNT="+str(len(data)))
    print("N07_PROBE_COLLABS="+",".join((u.get("login") or "") for u in data if isinstance(u, dict)))
else:
    print("N07_PROBE_COLLAB_COUNT=-1")
PY

admin_code=\$(curl -s -o /tmp/n07_admin.json -w "%{http_code}" -H "\$AUTH" \
  "\${BASE}/api/v1/admin/users?limit=1")
echo "N07_PROBE_ADMIN_USERS_HTTP=\${admin_code}"

del_code=\$(curl -s -o /tmp/n07_del.json -w "%{http_code}" -X DELETE -H "\$AUTH" \
  "\${BASE}/api/v1/repos/\${OWNER}/\${REPO}/collaborators/__n07_probe_nobody__")
echo "N07_PROBE_DELETE_NOBODY_HTTP=\${del_code}"

if [[ -n "\$DISP" ]]; then
  dcode=\$(curl -s -o /tmp/n07_disp_perm.json -w "%{http_code}" -H "\$AUTH" \
    "\${BASE}/api/v1/repos/\${OWNER}/\${REPO}/collaborators/\${DISP}/permission")
  echo "N07_PROBE_DISPOSABLE=\${DISP}"
  echo "N07_PROBE_DISPOSABLE_PERM_HTTP=\${dcode}"
  head -c 200 /tmp/n07_disp_perm.json; echo
  if [[ "\$dcode" == "200" || "\$dcode" == "404" ]]; then
    echo "N07_PROBE_VERDICT=disposable_ready"
  else
    echo "N07_PROBE_VERDICT=need_disposable_human"
  fi
else
  echo "N07_PROBE_DISPOSABLE="
  echo "N07_PROBE_DISPOSABLE_PERM_HTTP=skipped"
  echo "N07_PROBE_VERDICT=need_disposable_human"
fi
EOS
