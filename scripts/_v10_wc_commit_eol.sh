#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
git add \
  docs/adr/summary.md \
  docs/handoff/boss-ledger-v10.md \
  scripts/_v10_wc_fix_eol.sh \
  scripts/_v10_wc_fix_eol2.sh \
  scripts/_v10_wc_commit_eol.sh
git commit -m "$(cat <<'EOF'
Restore the original line endings on the two Wave C docs

A python rewrite of the ADR summary and the V10 ledger normalized both files to
LF, which turned two small edits into whole-file diffs. summary.md is CRLF in
git and boss-ledger-v10.md is LF; each is back to what it was.
EOF
)"
git push origin main
git rev-parse HEAD
git status --porcelain docs/
