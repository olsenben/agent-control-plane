#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/benol/Documents/Gitea/ai-sdlc-lab/agent-control-plane
.venv/bin/ruff check .
git add \
  docs/evidence/v10-wave-c/ \
  docs/handoff/coordinator-handoff-048.md \
  docs/handoff/deploy-verify-v10-wave-c-20260816.md \
  docs/handoff/boss-ledger-v10.md \
  scripts/_v10_wc_probe.sh \
  scripts/_v10_wc_probe2.sh \
  scripts/_v10_wc_probe3.sh \
  scripts/_v10_wc_scan2070.sh \
  scripts/_v10_wc_health.sh \
  scripts/_v10_wc_model_divergence.sh \
  scripts/_v10_wc_c1_live_smoke.py \
  scripts/_v10_wc_c1_live_run.sh \
  scripts/_v10_wc_negative_control.py \
  scripts/_v10_wc_negative_run.sh \
  scripts/_v10_wc_commit_push.sh \
  scripts/_v10_wc_commit_push2.sh \
  scripts/_v10_wc_commit_docs.sh
git commit -m "$(cat <<'EOF'
V10 Wave C: seal the live C1 attempt, deploy verification, and evidence

c1_proof is FAIL and the reason is hardware, not code: the RTX 2070 host msi has
been offline since roughly 12h before the wave, so the live C1 arm timed out and
controller_model_invoked is false. H1c stays unclaimed.

The contamination path the brief flagged is closed and proven live on both CT103
and CT104, with a negative control that forces an OpenAI-only candidate list and
records zero external HTTP attempts. New blocker recorded: CT103 and CT104 ask
the same 2070 endpoint for different models, so no C1 arm is comparable across
hosts until a human freezes that identity.
EOF
)"
git push origin main
git rev-parse HEAD
