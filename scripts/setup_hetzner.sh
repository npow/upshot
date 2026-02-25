#!/usr/bin/env bash
# Deploy upshot to Hetzner (188.34.193.79).
# Assumes Docker, Node, and Claude CLI are already installed and authenticated.
# Run as root: bash setup_hetzner.sh
set -euo pipefail

echo "=== Cloning repo ==="
git clone https://github.com/npow/upshot.git /root/upshot || echo "Already cloned"

echo "=== Creating .env ==="
if [ ! -f /root/upshot/.env ]; then
  cat > /root/upshot/.env <<'EOF'
GITHUB_TOKEN=<create PAT with repo scope at github.com/settings/tokens>
GIT_USER_NAME=Nissan Pow
GIT_USER_EMAIL=nissan.pow@gmail.com
EOF
  echo "⚠ Edit /root/upshot/.env and set GITHUB_TOKEN before first run"
else
  echo ".env already exists, skipping"
fi

echo "=== Starting services ==="
cd /root/upshot
docker compose up -d
echo "Services started. claude-relay will auto-restart on reboot."

echo "=== Done ==="
echo "Verify with: docker compose ps"
