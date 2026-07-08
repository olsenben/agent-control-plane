#!/usr/bin/env bash
# Git pull for CT103/CT104 deploy hosts — HTTP(S) + token only (no git@ :22).
# Token: DEPLOY_GIT_TOKEN env, or ~/.git-credentials from configure-deploy-git-https.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/ai-sdlc-lab/agent-control-plane}"
GIT_ORIGIN_URL="${GIT_ORIGIN_URL:-http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git}"
GIT_DEPLOY_USER="${GIT_DEPLOY_USER:-deploy}"

cd "$REPO_DIR"
git remote set-url origin "$GIT_ORIGIN_URL"

if [ -n "${DEPLOY_GIT_TOKEN:-}" ]; then
  ASKPASS="$(mktemp)"
  trap 'rm -f "$ASKPASS"' EXIT
  cat >"$ASKPASS" <<'EOS'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' "${GIT_DEPLOY_USER:-deploy}" ;;
  *Password*) printf '%s\n' "$DEPLOY_GIT_TOKEN" ;;
esac
EOS
  chmod 700 "$ASKPASS"
  export GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0
elif [ ! -f "${HOME}/.git-credentials" ]; then
  echo "No DEPLOY_GIT_TOKEN and no ~/.git-credentials — run configure-deploy-git-https.sh" >&2
  exit 1
fi

git fetch origin main

# Deploy hosts may have manual bootstrap copies or hand-edited tracked files; sync to
# origin/main (.env and other gitignored host secrets stay untouched).
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ -e "$path" ] && ! git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    rm -rf "$path"
  fi
done < <(git ls-tree -r --name-only origin/main)

git checkout -f main
git reset --hard origin/main
