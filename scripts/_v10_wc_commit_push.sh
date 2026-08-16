#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
git add \
  src/agent_control/recursive_context/model_client.py \
  src/agent_control/recursive_context/telemetry.py \
  src/agent_control/recursive_context/worker.py \
  src/agent_shared/models/recursive_context.py \
  tests/test_v10_t005_controller_backend.py \
  docs/slice-v10-wave-c-c1-local-only.md
git commit -m "$(cat <<'EOF'
V10 Wave C: make the C1 controller local-only and stop faking absent timings

A C1 observation only means "the real 2070 answered" if no other route could
have. The 2070 tier carries an OpenAI fallback with a live key on CT103/CT104,
and only an empty REPO_EXTERNAL_MODEL_POLICY was keeping it unreachable. The
controller now checks every route the failover chain offers before sending
anything and refuses non-homelab providers outright, so the boundary no longer
depends on an env var.

Absent endpoint timings were recorded as 0.0, which reads as a measured value.
controller_gpu_seconds is now nullable and unreported metrics are named in
controller_missing_fields, which maintenance-evals already treats as missing.

Evaluated C1 behaviour is unchanged: same role, prompt, budgets, sampling,
recursion trigger, and read-only authority; config/recursive_context.yaml is
untouched.
EOF
)"
git rev-parse HEAD
git push origin main
git rev-parse HEAD
