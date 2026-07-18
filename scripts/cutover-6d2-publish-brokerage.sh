#!/usr/bin/env bash
# Barrier cutover checklist for V4.1.1 CT103 publish brokerage.
# Run from a supervising shell; do not automate token rotation blindly.
#
# See docs/slice-6d2-ct103-publish-brokerage.md

set -euo pipefail

echo "1) Disable FIX_REMOTE_PUBLISH_ENABLED on CT103 (brokerage off) and pause fix/repair enqueue if needed"
echo "2) Drain CT104 rlm-root / ci-repair / report queues; confirm no in-flight publish stage"
echo "3) Deploy CT103 with publish-broker service (workers profile); keep FIX_REMOTE_PUBLISH_ENABLED=false"
echo "4) Deploy CT104 bundle-only workers from current main"
echo "5) On CT104: unset GITEA_BOT_TOKEN and GITEA_AGENT_TOKEN; recreate containers"
echo "6) Rotate/revoke tokens that were ever present on CT104; ensure GITEA_BOT_TOKEN only on CT103"
echo "7) Confirm CT104 worker starts (no WorkerCredentialError)"
echo "8) Enable FIX_REMOTE_PUBLISH_ENABLED=true on CT103; recreate publish-broker"
echo "9) Fix E2E: patch_bundle_ready → broker PR → 6E pending"
echo "10) Repair E2E: repair_bundle_ready → broker FF push → pending re-point"
echo "11) Re-enable normal enqueueing"
echo
echo "Manual ops required — this script only prints the barrier order."
