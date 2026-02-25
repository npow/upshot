#!/usr/bin/env bash
# Deploy upshot to Hetzner (188.34.193.79).
# Assumes Docker, Node, and Claude CLI are already installed and authenticated.
# Run as root: bash setup_hetzner.sh
set -euo pipefail

echo "=== Cloning repo ==="
git clone git@github.com:npow/upshot.git /root/upshot || echo "Already cloned"

cd /root/upshot
git submodule update --init --recursive

echo "=== Configuring git identity ==="
git config user.name "Nissan Pow"
git config user.email "nissan.pow@gmail.com"

echo "=== Creating .env ==="
if [ ! -f .env ]; then
  cat > .env <<'EOF'
GIT_USER_NAME=Nissan Pow
GIT_USER_EMAIL=nissan.pow@gmail.com
EOF
fi

echo "=== Starting services ==="
docker compose up -d
echo "Services started. claude-relay will auto-restart on reboot."

echo "=== Done ==="
echo "Verify with: docker compose ps"
