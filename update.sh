#!/usr/bin/env bash
# Usage: ./update.sh [/path/to/food]
# Copies <food>/recipes/*.md into ./food/recipes (mirror: removed recipes disappear),
# fetches photos only for recipes that still need one, rebuilds the site, commits
# "kitchen: update <date>" and pushes to main. With no argument, rebuilds from ./food as-is.
# Only the recipes/ folder is copied; other private food/ files are never published.
set -euo pipefail
cd "$(dirname "$0")"
if [ $# -gt 1 ]; then echo "usage: $0 [path/to/food]" >&2; exit 2; fi
git pull --ff-only --quiet origin main || true
if [ $# -eq 1 ]; then
  SRC="$(cd "$1" && pwd)/recipes"
  [ -d "$SRC" ] && ls "$SRC"/*.md >/dev/null 2>&1 || { echo "no recipes in $SRC" >&2; exit 2; }
  if [ "$SRC" != "$(pwd)/food/recipes" ]; then
    mkdir -p food/recipes
    rsync -a --delete --include='*.md' --exclude='*' "$SRC"/ food/recipes/
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
