#!/usr/bin/env bash
# Quick CT104 acceptance checks. Run on CT104.
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/ai-sdlc-lab/agent-control-plane}"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.ct104.yml"

cd "$COMPOSE_DIR"

echo "== compose services =="
docker compose -f "$COMPOSE_FILE" ps

echo "== worker doctor =="
docker compose -f "$COMPOSE_FILE" exec -T worker-rlm-root agentctl worker doctor

if [ -f "${GIT_CREDENTIALS_HOST_PATH:-/home/deploy/.git-credentials}" ]; then
  echo "== git clone smoke (worker-rlm-root) =="
  docker compose -f "$COMPOSE_FILE" exec -T worker-rlm-root python -c "
from pathlib import Path
import shutil, subprocess
from agent_control.git_auth import authenticated_repo_url_from_credentials, git_non_interactive_env
url = authenticated_repo_url_from_credentials(
    'http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git'
)
dest = Path('/tmp/verify-clone-test')
if dest.exists():
    shutil.rmtree(dest)
env = git_non_interactive_env(repo_url=url)
subprocess.run(
    ['git', 'clone', '--depth', '1', '--branch', 'main', url, str(dest)],
    check=True,
    env=env,
)
assert (dest / 'README.md').is_file()
print('clone ok')
"
else
  echo "skip git clone smoke — no ${GIT_CREDENTIALS_HOST_PATH:-/home/deploy/.git-credentials}"
fi

echo "CT104 checks complete."
