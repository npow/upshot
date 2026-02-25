#!/usr/bin/env bash
# Container entrypoint: run pipeline → publish Hugo post → push to GitHub.
set -e

DATE=$(date +%Y-%m-%d)
echo "=== upshot daily run: $DATE ==="

# Run the full pipeline (no resume — clean daily run)
upshot run --no-resume

# Publish digest as a Hugo blog post
python /app/scripts/publish_post.py "$DATE"

# Configure git
git -C /app config user.email "$GIT_USER_EMAIL"
git -C /app config user.name "$GIT_USER_NAME"

# Commit and push if there are changes
git -C /app add blog/content/posts/
if ! git -C /app diff --cached --quiet; then
  git -C /app commit -m "briefing: $DATE"
  git -C /app push \
    "https://${GITHUB_TOKEN}@github.com/npow/upshot.git" main
  echo "Pushed briefing for $DATE"
else
  echo "No new content to push"
fi
