#!/usr/bin/env bash
# Run on CT104 (agent-worker). Idempotent UFW — no inbound services required.
set -euo pipefail
sudo ufw default deny incoming
sudo ufw allow from 192.168.4.0/22 to any port 22 proto tcp comment 'SSH from LAN'
sudo ufw --force enable
sudo ufw status verbose
