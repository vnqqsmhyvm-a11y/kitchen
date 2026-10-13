# kitchen

Family recipe library (link-only, `noindex`), built from the recipe cards in `food/recipes/*.md`.
Live: https://vnqqsmhyvm-a11y.github.io/kitchen/

- `./update.sh /path/to/personal-kb/food` — copy that folder's `recipes/*.md` in, fetch photos for recipes that still need one, rebuild, commit, push. Only `recipes/` is copied.
- `./update.sh` — same, but rebuild from the `food/recipes` already here.
- `python3 build.py [food]` — rebuild pages only (home `index.html`, `recipes/<slug>/`, `week/` stub).
- `python3 fetch_photos.py [food] [--retry]` — one quick photo attempt per recipe: card `**Photo:**` URL → `photo_urls.json` (known media, e.g. X post images) → source page `og:image`. Saves `photos/<slug>.jpg` (≤1200px, JPEG q80). Never searches, generates, or hotlinks.

`photos.json`: slug → `{path, source, credit, status, checked}`. `ok` = has a photo; `missing` = worth another try (X post without a known media URL, or the source site's bot-check blocked us — retried at most weekly); `unavailable` = no photo/web source on the card. `--retry` re-tries everything not `ok`. To add an X photo, look up the post's media URL and add it to `photo_urls.json`.

Privacy: `build.py` strips family names, approval/dislike lines, private notes and links to private vault files at render time (the markdown is never edited), then fails the build if any family name or private path remains in the HTML.

Needs: python3 with pillow and requests; rsync.
