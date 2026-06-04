#!/usr/bin/env bash
# Run on CT103 (agent-control). Idempotent UFW for LAN-only AgentControl.
set -euo pipefail
sudo ufw default deny incoming
sudo ufw allow from 192.168.4.0/22 to any port 8080 proto tcp comment 'AgentControl LAN'
sudo ufw deny 6379/tcp comment 'Redis not on LAN'
sudo ufw --force enable
sudo ufw status verbose
