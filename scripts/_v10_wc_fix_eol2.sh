#!/usr/bin/env bash
# boss-ledger-v10.md is LF in git; summary.md is CRLF. Match each.
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
python3 - <<'PY'
from pathlib import Path
p = Path("docs/handoff/boss-ledger-v10.md")
p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
print("lf", p)
PY
git diff --stat 027ad9f -- docs/adr/summary.md docs/handoff/boss-ledger-v10.md
