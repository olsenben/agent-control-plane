#!/usr/bin/env bash
# V6 T04 chaos / smoke: budget + failover + egress (in-container, no live GPU kill required)
set -euo pipefail
KEY="${HOME}/.ssh/.ct103_deploy"
TIP="${1:?short tip}"
TIP="${TIP:0:7}"

bash /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane/scripts/_wait_tip_57.sh "$TIP"

ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
cat > /tmp/v6_t04_smoke.py <<'PY'
from pathlib import Path
import tempfile

from agent_control.config import Settings
from agent_control.model_gateway import (
    ModelRouteExhausted,
    chat_completion_with_failover,
    context_controller_policy,
)
from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.model_attempt_budget import AttemptBudgetTracker, ModelAttemptBudget

assert context_controller_policy(recursion_needed=True, controller_available=False) == "deterministic_only"

root = Path(tempfile.mkdtemp())
settings = Settings(
    MODEL_3080_BASE_URL="http://127.0.0.1:9",
    MODEL_3080_NAME="qwen",
    MODEL_3080_FALLBACK_BASE_URL="https://api.example.com/v1",
    MODEL_3080_FALLBACK_NAME="gpt-mini",
    MODEL_3080_FALLBACK_API_KEY="sk",
    MODEL_FALLBACK_ENABLED=True,
    REPO_EXTERNAL_MODEL_POLICY="ai-sdlc-lab/*",
    MODEL_CODE_HANDLING_ROLES="reviewer,fixer,rlm",
    AGENT_STATE_ROOT=root,
)

calls = []

def fake(endpoint: ResolvedEndpoint, **kwargs):
    calls.append(endpoint.provider)
    if endpoint.provider == "gpu":
        raise ConnectionError("simulated 3080 down")
    return {"content": "ok", "model": endpoint.model, "provider": endpoint.provider,
            "base_url": endpoint.base_url, "usage": {}}

result = chat_completion_with_failover(
    "reviewer",
    system_prompt="s",
    user_prompt="u",
    project="ai-sdlc-lab/demo-app",
    run_id="run-v6-t04-chaos",
    state_root=root,
    settings=settings,
    complete_fn=fake,
)
assert result["fallback_used"] is True
assert "fallback" in calls

# Egress deny -> all routes failed when GPU down
deny = Settings(
    MODEL_3080_BASE_URL="http://127.0.0.1:9",
    MODEL_3080_NAME="qwen",
    MODEL_3080_FALLBACK_BASE_URL="https://api.example.com/v1",
    MODEL_3080_FALLBACK_NAME="gpt-mini",
    MODEL_FALLBACK_ENABLED=True,
    REPO_EXTERNAL_MODEL_POLICY="",
    AGENT_STATE_ROOT=root,
)
try:
    chat_completion_with_failover(
        "reviewer", system_prompt="s", user_prompt="u",
        project="ai-sdlc-lab/demo-app", run_id="run-v6-t04-deny",
        state_root=root, settings=deny, complete_fn=fake,
    )
    raise SystemExit("expected ModelRouteExhausted")
except ModelRouteExhausted:
    pass

budget = AttemptBudgetTracker(limits=ModelAttemptBudget(max_total_completion_attempts=1))
assert budget.consume("infrastructure")
assert not budget.consume("infrastructure")
print("V6_T04_SMOKE_OK", "fallback", result.get("data_left_homelab"), "budget_ok")
PY
CID=$(docker compose ps -q control-plane)
docker cp /tmp/v6_t04_smoke.py "$CID":/tmp/v6_t04_smoke.py
docker compose exec -T control-plane python /tmp/v6_t04_smoke.py </dev/null
EOS

echo DEPLOY_SMOKE_V6_T04_PASS tip=$TIP
