# kitchen

Family recipe library and weekly meal plan (link-only, `noindex`), built from `food/recipes/*.md` and `food/plans/*.md`.
Live: https://vnqqsmhyvm-a11y.github.io/kitchen/ · This Week: https://vnqqsmhyvm-a11y.github.io/kitchen/week/

- `./update.sh /path/to/personal-kb/food` — copy that folder's `recipes/*.md`, `plans/*.md`, and `queued-recipes.md` in, fetch photos for recipes that still need one, rebuild library + This Week, commit, push. Private markdown stays in gitignored `food/`; only scrubbed HTML is published.
- `./update.sh` — same, but rebuild from the `food/` already here.
- `python3 build.py [food]` — rebuild pages only (home `index.html`, `recipes/<slug>/`, `week/` with current schedule, queued list, and past-week archive).
- `python3 fetch_photos.py [food] [--retry]` — one quick photo attempt per recipe: card `**Photo:**` URL → `photo_urls.json` (known media, e.g. X post images) → source page `og:image`. Saves `photos/<slug>.jpg` (≤1200px, JPEG q80). Never searches, generates, or hotlinks.

`photos.json`: slug → `{path, source, credit, status, checked}`. `ok` = has a photo; `missing` = worth another try (X post without a known media URL, or the source site's bot-check blocked us — retried at most weekly); `unavailable` = no photo/web source on the card. `--retry` re-tries everything not `ok`. To add an X photo, look up the post's media URL and add it to `photo_urls.json`.

Privacy: `build.py` strips family names, approval/dislike lines, private notes and links to private vault files at render time (the markdown is never edited). The week page publishes only day→dinner, the upcoming queue, and a past-weeks archive (no grocery lists, quotas, verdicts, or medication notes). The build fails if any family name or private path remains in the HTML.

Needs: python3 with pillow and requests.

`food/` is git-ignored: the raw cards and plans contain family names and private notes, so only the scrubbed HTML is published.
