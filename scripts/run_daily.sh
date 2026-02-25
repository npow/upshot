#!/usr/bin/env bash
# Container entrypoint: run pipeline → publish Hugo post.
# Git push happens on the host (see daily.yml / setup_hetzner.sh).
set -e

DATE=$(date +%Y-%m-%d)
echo "=== upshot daily run: $DATE ==="

# Run the full pipeline (no resume — clean daily run)
upshot run --no-resume

# Publish digest as a Hugo blog post
python /app/scripts/publish_post.py "$DATE"

echo "=== pipeline complete ==="
