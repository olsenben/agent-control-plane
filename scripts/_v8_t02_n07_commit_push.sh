#!/usr/bin/env bash
# Commit+push V8 T02 only. Stop on rebase conflict.
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane

.venv/bin/ruff check .

git add \
  src/agent_control/authorization.py \
  src/agent_control/gitea_client.py \
  tests/test_qa_v6_wave3.py \
  tests/test_v8_t02_n07.py \
  scripts/_v8_t02_n07_live.sh \
  scripts/_v8_t02_n07_probe.sh \
  scripts/_v8_t02_n07_commit_push.sh \
  docs/slice-v8-t02-n07-live.md \
  docs/handoff/coordinator-handoff-023.md \
  docs/handoff/evidence/v8-t02-n07-probe.txt \
  docs/handoff/evidence/v8-t02-n07-20260721T231839Z.txt

git diff --cached --stat
git commit -m "$(cat <<'EOF'
feat(v8-t02): N07 publish deny after approver collaborator revoke

Publish recheck requires live repo write for the recorded approver; fix
permission 404 fallback so revoked collaborators do not inherit bot admin.
Harness + hermetic tests; live proof WaitingHuman for disposable user.
EOF
)"

TIP=$(git rev-parse --short=7 HEAD)
sed -i "s/(pending commit)/${TIP}/" docs/handoff/coordinator-handoff-023.md
git add docs/handoff/coordinator-handoff-023.md
git commit -m "docs(v8-t02): pin handoff 023 tip SHA"

# Clear dirty tree so rebase can run; restore afterward for sibling agents.
git stash push -u -m "v8-t02-temp-unrelated-wip"

git fetch origin
git pull --rebase origin main
git push origin HEAD

echo "TIP=$(git rev-parse HEAD)"
git stash pop || true
git status -sb
git log -3 --oneline
