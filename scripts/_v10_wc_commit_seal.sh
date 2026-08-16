#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
git add \
  docs/handoff/coordinator-handoff-048.md \
  docs/handoff/boss-ledger-v10.md \
  scripts/_v10_wc_final_check.sh \
  scripts/_v10_wc_commit_seal.sh
git commit -m "$(cat <<'EOF'
V10 Wave C: separate the deployed SHA from the docs tip

The runtime CT103 and CT104 are pinned to is 027ad9f; everything after it is
docs-only sealing. Recording both so the next coordinator does not read the docs
tip as the verified deployment.
EOF
)"
git push origin main
git rev-parse HEAD
