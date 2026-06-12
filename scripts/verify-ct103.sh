#!/usr/bin/env bash
# Quick CT103 acceptance checks. Run on CT103 or any host that can reach it.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/ai-sdlc-lab/agent-control-plane}"

echo "== healthz =="
curl -sf "${BASE_URL}/healthz" | python3 -m json.tool

echo "== readyz =="
curl -sf "${BASE_URL}/readyz" | python3 -m json.tool

if [ -d "$COMPOSE_DIR" ]; then
  echo "== compose services =="
  docker compose -f "${COMPOSE_DIR}/docker-compose.yml" --profile workers ps

  echo "== redis persistence probe =="
  docker compose -f "${COMPOSE_DIR}/docker-compose.yml" exec -T redis redis-cli ping

  echo "== state queue depth =="
  docker compose -f "${COMPOSE_DIR}/docker-compose.yml" exec -T control-plane \
    agentctl queue info 2>/dev/null | python3 -m json.tool || true
fi

echo "CT103 checks complete."
