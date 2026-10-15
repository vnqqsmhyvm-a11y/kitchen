#!/usr/bin/env bash
# Usage: ./update.sh [/path/to/food]
# Copies <food>/recipes/*.md into ./food/recipes (mirror: removed recipes disappear),
# and when given a path also copies plans/*.md + queued-recipes.md into ./food/
# (private markdown stays gitignored; only scrubbed HTML is published).
# Fetches photos only for recipes that still need one, rebuilds library + This Week,
# commits "kitchen: update <date>" and pushes to main.
# With no argument, rebuilds from ./food as-is.
set -euo pipefail
cd "$(dirname "$0")"
if [ $# -gt 1 ]; then echo "usage: $0 [path/to/food]" >&2; exit 2; fi
git pull --ff-only --quiet origin main || true
if [ $# -eq 1 ]; then
  SRC_ROOT="$(cd "$1" && pwd)"
  SRC="$SRC_ROOT/recipes"
  [ -d "$SRC" ] && ls "$SRC"/*.md >/dev/null 2>&1 || { echo "no recipes in $SRC" >&2; exit 2; }
  if [ "$SRC" != "$(pwd)/food/recipes" ]; then
    mkdir -p food/recipes
    find food/recipes -maxdepth 1 -name '*.md' -delete
    cp "$SRC"/*.md food/recipes/
  fi
  # plans + queue (needed for This Week); never published as markdown
  mkdir -p food/plans
  find food/plans -maxdepth 1 -name '*.md' -delete
  if [ -d "$SRC_ROOT/plans" ] && ls "$SRC_ROOT/plans"/*.md >/dev/null 2>&1; then
    cp "$SRC_ROOT/plans"/*.md food/plans/
  fi
  if [ -f "$SRC_ROOT/queued-recipes.md" ]; then
    cp "$SRC_ROOT/queued-recipes.md" food/queued-recipes.md
  fi
fi
python3 fetch_photos.py food
python3 build.py food
git add -A index.html recipes week assets photos photos.json photo_urls.json \
  robots.txt .nojekyll build.py fetch_photos.py update.sh README.md .gitignore
if git diff --cached --quiet; then
  echo "no changes; nothing to commit"
else
  git commit --quiet -m "kitchen: update $(TZ=America/Chicago date +%Y-%m-%d)"
fi
git push --quiet origin HEAD:main
echo "live: https://vnqqsmhyvm-a11y.github.io/kitchen/"
echo "week: https://vnqqsmhyvm-a11y.github.io/kitchen/week/"
