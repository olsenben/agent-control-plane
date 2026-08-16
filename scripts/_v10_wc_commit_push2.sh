#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
git add \
  src/agent_control/recursive_context/model_client.py \
  src/agent_control/recursive_context/telemetry.py \
  src/agent_control/recursive_context/worker.py \
  src/agent_shared/models/recursive_context.py \
  src/agent_workers/rlm/completion.py \
  tests/test_v10_t005_controller_backend.py \
  docs/slice-v10-wave-c-c1-local-only.md
git commit -m "$(cat <<'EOF'
V10 Wave C: record which model the endpoint actually served

Handoff 035 claimed controller_model_id was read back from the endpoint, but
chat_completion preferred the configured MODEL_2070_NAME, so a 2070 serving a
different model would still have been recorded as qwen2.5-coder:3b. That makes
the id unusable as C1 evidence.

chat_completion now also returns model_reported and the controller prefers it,
tagging controller_model_id_source as endpoint_reported, configured, or
planned_not_invoked so an auditor can tell an observation from a config echo.
EOF
)"
git push origin main
git rev-parse HEAD
