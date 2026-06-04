#!/usr/bin/env bash
# Run on CT102 (steelleg Gitea runner). Outbound-only; no inbound services required.
set -euo pipefail
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw --force enable
sudo ufw status verbose
