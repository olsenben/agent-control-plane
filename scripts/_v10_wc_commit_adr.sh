#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
git add \
  docs/adr/0033-c1-controller-local-only-egress-boundary.md \
  docs/adr/summary.md \
  scripts/_v10_wc_commit_adr.sh
git commit -m "$(cat <<'EOF'
ADR-0033 (proposed): local-only egress boundary for the C1 recursive controller

Records why the C1 controller stopped inheriting the shared failover chain's
egress permissions. The homelab boundary previously held only because
REPO_EXTERNAL_MODEL_POLICY happened to be empty, which is configuration rather
than architecture.
EOF
)"
git push origin main
git rev-parse HEAD
