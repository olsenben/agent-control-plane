#!/usr/bin/env bash
# VExp W1 deploy verify: pin CT103+CT104, rebuild, W1 context_mode smoke.
set -euo pipefail

KEY="${HOME}/.ssh/.ct103_deploy"
APP="/opt/ai-sdlc-lab/agent-control-plane"
TIP="${1:?usage: _vexp_w1_deploy_verify.sh <full-sha>}"
SKIP_REBUILD="${SKIP_REBUILD:-0}"

if [ "$SKIP_REBUILD" != "1" ]; then
echo "=== CT103 pull + rebuild ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 -i "$KEY" deploy@192.168.4.62 bash -s <<EOS
set -euo pipefail
cd ${APP}
bash scripts/deploy-git-pull.sh
HEAD=\$(git rev-parse HEAD)
echo "CT103_TIP=\$HEAD"
test "\$HEAD" = "${TIP}"
docker compose --profile workers build control-plane worker-state publish-broker
docker compose --profile workers up -d control-plane worker-state publish-broker
status=""
for i in \$(seq 1 30); do
  http_code="\$(curl -s -o /tmp/readyz.json -w '%{http_code}' --connect-timeout 3 \
    http://127.0.0.1:8080/readyz 2>/dev/null || echo 000)"
  if [ -f /tmp/readyz.json ] && [ -s /tmp/readyz.json ]; then
    status="\$(python3 -c "import json; print(json.load(open('/tmp/readyz.json')).get('status',''))" 2>/dev/null || true)"
    if [ "\$status" = "ready" ] || [ "\$status" = "degraded" ]; then
      echo "CT103_READYZ=\$status http=\$http_code"
      break
    fi
  fi
  echo "readyz wait \$i: http=\$http_code status=\${status:-unknown}"
  sleep 2
done
if [ "\$status" != "ready" ] && [ "\$status" != "degraded" ]; then
  echo "readyz did not reach ready/degraded" >&2
  exit 1
fi
test -n "\$(docker compose --profile workers ps --status running -q worker-state)"
echo "worker-state: running"
python3 -c "import json; d=json.load(open('/tmp/readyz.json')); print('CT103_READYZ_REDIS='+str(d.get('redis') or d))"
EOS

echo "=== CT104 pull + rebuild + write-token floor ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 -i "$KEY" deploy@192.168.4.63 bash -s <<EOS
set -euo pipefail
cd ${APP}
bash scripts/deploy-git-pull.sh
HEAD=\$(git rev-parse HEAD)
echo "CT104_TIP=\$HEAD"
test "\$HEAD" = "${TIP}"
docker compose -f docker-compose.ct104.yml build worker-rlm-root worker-report worker-ci-repair
docker compose -f docker-compose.ct104.yml up -d worker-rlm-root worker-report worker-ci-repair
sleep 4
for svc in worker-rlm-root worker-report worker-ci-repair; do
  if [ -z "\$(docker compose -f docker-compose.ct104.yml ps --status running -q "\$svc")" ]; then
    echo "\$svc is not running" >&2
    exit 1
  fi
  echo "\$svc: running"
done
docker compose -f docker-compose.ct104.yml exec -T worker-rlm-root agentctl worker doctor </dev/null
docker compose -f docker-compose.ct104.yml ps -q | while read -r cid; do
  name=\$(docker inspect -f '{{.Name}}' "\$cid")
  hit=\$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "\$cid" \
    | grep -E '^(GITEA_[A-Z_]*(TOKEN|PASSWORD)|AGENT_STATE_TOKEN)=' || true)
  if [ -n "\$hit" ]; then echo "FAIL_GITEA_WRITE \$name"; exit 1; fi
  echo "gitea_write_absent \$name"
done
echo "CT104_GITEA_WRITE_FLOOR_OK"
docker compose -f docker-compose.ct104.yml exec -T worker-rlm-root python3 -c \
  "from agent_workers.rlm.official_engine import render_job_context_pack; from agent_control.context.v1_adapter import render_v2; print('CT104_RENDER_IMPORT_OK')" \
  </dev/null
EOS
fi

echo "=== CT103 W1 eval-dispatch smoke (fake engine) ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
rm -rf /tmp/w1-eval-ws
cp -a tests/fixtures/vexp_mini_repo /tmp/w1-eval-ws
cd /tmp/w1-eval-ws
git init -q .
git config user.email probe@localhost
git config user.name probe
git add -A
git commit -qm "w1 probe"
SHA=$(git rev-parse HEAD)
cd /opt/ai-sdlc-lab/agent-control-plane
cat > /tmp/_vexp_w1_container_smoke.py <<PY
import json
import os
from pathlib import Path
from agent_control.eval_dispatch import dispatch_evaluation, get_session, session_root

sha = ${SHA@Q}
workspace = "/tmp/w1-eval-ws"
# docker cp leaves host-owned files; git refuses them without safe.directory.
os.environ["GIT_CONFIG_COUNT"] = "1"
os.environ["GIT_CONFIG_KEY_0"] = "safe.directory"
os.environ["GIT_CONFIG_VALUE_0"] = "*"
modes = ("baseline_v1", "context_v2_lexical", "context_v2")
for mode in modes:
    req = {
        "schema": "maintenance_eval_dispatch.v1",
        "eval_run_id": f"w1-deploy-{mode}",
        "project": "vexp/mini",
        "workspace": workspace,
        "head_sha": sha,
        "policy_source_sha": "b" * 40,
        "problem_statement": "Fix foo in src/pkg/foo.py",
        "arm": "local-deterministic",
        "context_strategy": "deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 60, "attempts": 1},
        "evaluation_mode": "retrieval",
        "upstream_task_id": "w1-smoke",
        "context_mode": mode,
    }
    sid = dispatch_evaluation(req)
    record = get_session(sid, "vexp/mini")
    tel = record.get("evaluation_telemetry") or {}
    print(f"SMOKE_{mode}_SESSION={sid}")
    print(f"SMOKE_{mode}_STATUS={record.get('status')}")
    print(f"SMOKE_{mode}_CONTEXT_MODE={tel.get('context_mode')}")
    print(f"SMOKE_{mode}_PACK_VERSION={tel.get('context_pack_version')}")
    print(f"SMOKE_{mode}_PACK_HASH={tel.get('context_pack_hash')}")
    print(f"SMOKE_{mode}_RENDERED_HASH={tel.get('rendered_context_hash')}")
    print(f"SMOKE_{mode}_PROVIDERS={tel.get('evidence_provider_ids')}")
    print(f"SMOKE_{mode}_REPAIR={tel.get('repair_attempts')}")
    assert tel.get("agent_execution") is True, tel
    assert int(tel.get("repair_attempts") or 0) == 0, tel
    assert not tel.get("recursive_invoked"), tel
    if mode in ("context_v2", "context_v2_lexical"):
        assert tel.get("context_pack_version") == "context-pack.v2", tel
        assert tel.get("context_pack_hash"), tel
        assert tel.get("rendered_context_hash"), tel
        assert not tel.get("treatment_integrity_failed"), tel
        msg = None
        art = Path(str((record.get("eval_dispatch") or {}).get("artifact_dir") or ""))
        candidate = art / "official_engine_messages.json"
        if candidate.is_file():
            msg = candidate
        else:
            for p in Path(str(session_root())).rglob("official_engine_messages.json"):
                msg = p
                break
        assert msg is not None and msg.is_file(), f"missing messages for {mode}"
        user = json.loads(msg.read_text()).get("user") or ""
        assert "=== context-pack.v2 ===" in user, user[:500]
        assert "=== context_pack.v1 ===" not in user
        print(f"SMOKE_{mode}_V2_PROMPT=yes")
    print(f"SMOKE_{mode}_OK")
print("W1_EVAL_SMOKE_OK")

class _ParseTimeout:
    def run(self, job, workspace, policy, *, artifact_dir=None, **kwargs):
        from pathlib import Path as _P
        art = _P(str(artifact_dir))
        treat = art / "treatment_exposure.json"
        pack = art / "context_pack.json"
        rendered = art / "rendered_context.txt"
        assert treat.is_file(), art
        assert pack.is_file()
        assert rendered.is_file()
        payload = json.loads(treat.read_text())
        assert payload.get("context_pack_hash")
        assert payload.get("rendered_context_hash")
        assert payload.get("context_pack_version") == "context-pack.v2"
        assert payload.get("sequence_position") == "pre_model_invocation"
        raise ValueError(
            "Failed to parse fix output: Expecting ',' delimiter: line 9 column 20 (char 459); "
            "json retry failed: timed out; missing-json repair failed: timed out"
        )

sid = dispatch_evaluation(
    {
        "schema": "maintenance_eval_dispatch.v1",
        "eval_run_id": "w1-deploy-parse-timeout",
        "project": "vexp/mini",
        "workspace": workspace,
        "head_sha": sha,
        "policy_source_sha": "b" * 40,
        "problem_statement": "Fix foo in src/pkg/foo.py",
        "arm": "local-deterministic",
        "context_strategy": "deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 60, "attempts": 1},
        "evaluation_mode": "patch",
        "upstream_task_id": "w1-smoke-parse",
        "context_mode": "context_v2",
    },
    engine_factory=lambda _name: _ParseTimeout(),
)
record = get_session(sid, "vexp/mini")
tel = record.get("evaluation_telemetry") or {}
art = Path(str((record.get("eval_dispatch") or {}).get("artifact_dir") or ""))
treat = json.loads((art / "treatment_exposure.json").read_text())
assert record.get("status") == "failed"
assert record.get("terminal_reason_code") == "evaluated_agent"
assert tel.get("context_pack_version") == "context-pack.v2"
assert tel.get("context_pack_hash") == treat["context_pack_hash"]
assert tel.get("rendered_context_hash") == treat["rendered_context_hash"]
assert tel.get("repair_attempts") == 0
assert not tel.get("recursive_invoked")
print(f"SMOKE_parse_timeout_SESSION={sid}")
print(f"SMOKE_parse_timeout_PACK_HASH={tel.get('context_pack_hash')}")
print("SMOKE_parse_timeout_TREATMENT_OK")

from agent_control.config import Settings
from agent_control.context.v2_dispatch import (
    CONTEXT_MODE_BASELINE_V1,
    resolve_production_context_mode,
)
from agent_control.context.workspace import materialize_exact_sha_workspace
from agent_control.graph.context_pack import compile_context_pack

live = Settings()
assert resolve_production_context_mode(live) == CONTEXT_MODE_BASELINE_V1, live.context_mode
defaults = Settings(_env_file=None)
assert defaults.context_mode == CONTEXT_MODE_BASELINE_V1
assert callable(compile_context_pack)
print("PROD_DEFAULT_COMPILE_CONTEXT_PACK_OK")
ws = materialize_exact_sha_workspace(
    repo_url=str(Path(workspace).resolve()),
    target_sha=sha,
    dest="/tmp/w1-exact-sha-copy",
)
head = __import__("subprocess").check_output(
    ["git", "rev-parse", "HEAD"], cwd=ws, text=True
).strip()
assert head == sha, (head, sha)
print(f"PROD_EXACT_SHA_WORKSPACE_OK={head}")
PY
docker compose --profile workers exec -T control-plane rm -rf /tmp/w1-eval-ws /tmp/w1-exact-sha-copy /tmp/w1-eval-sessions </dev/null
docker compose --profile workers cp /tmp/w1-eval-ws control-plane:/tmp/w1-eval-ws
docker compose --profile workers exec -T -u 0 control-plane chown -R root:root /tmp/w1-eval-ws </dev/null
docker compose --profile workers cp /tmp/_vexp_w1_container_smoke.py control-plane:/tmp/_vexp_w1_container_smoke.py
docker compose --profile workers exec -T \
  -e EVAL_DISPATCH_ENGINE=fake \
  -e EVAL_DISPATCH_SESSION_ROOT=/tmp/w1-eval-sessions \
  control-plane python3 /tmp/_vexp_w1_container_smoke.py </dev/null
EOS

echo "VEXP_W1_DEPLOY_VERIFY_SCRIPT_DONE"
echo "TIP=${TIP}"
