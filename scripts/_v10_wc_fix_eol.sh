#!/usr/bin/env bash
# Restore the repo's CRLF convention on the two docs a python rewrite flattened.
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
for f in docs/adr/summary.md docs/handoff/boss-ledger-v10.md; do
  python3 - "$f" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
data = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
p.write_bytes(data)
print(f"crlf {p}")
PY
done
echo "--- diff stat vs HEAD ---"
git diff --stat docs/adr/summary.md docs/handoff/boss-ledger-v10.md
echo "--- diff stat vs pre-wave-c ---"
git diff --stat 027ad9f -- docs/adr/summary.md docs/handoff/boss-ledger-v10.md
