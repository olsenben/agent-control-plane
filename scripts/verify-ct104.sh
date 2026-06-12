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

echo "CT104 checks complete."
