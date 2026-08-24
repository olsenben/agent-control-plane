#!/usr/bin/env bash
# Thin ACP wrapper. Real script: maintenance-evals/scripts/w5_live_evidence_ct103.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${HERE}/../../maintenance-evals/scripts/w5_live_evidence_ct103.sh" "$@"
