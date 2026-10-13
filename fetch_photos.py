#!/usr/bin/env python3
"""Fetch one real photo per recipe, cheaply. Never invents or searches for images.

Usage: python3 fetch_photos.py [path/to/food] [--retry]

Per recipe, ONE quick attempt, in this order:
  1. the card's **Photo:** URL
  2. photo_urls.json (known media URLs, e.g. X post images looked up once with the X tools)
  3. the card's **Source:** web page -> og:image / twitter:image (skips logos/placeholders)
X-post sources with no known media URL stay "missing" (needs a one-off X lookup).
Saves photos/<slug>.jpg (<=1200px wide, JPEG q80) and records photos.json:
  slug -> {path, source, credit, status: ok|missing|unavailable, checked}
Later runs only try "missing" recipes (at most weekly for bot-blocked pages);
"unavailable" means the card has no usable photo/web source. --retry re-tries everything not ok.
"""
import datetime as dt
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
RETRY = "--retry" in sys.argv
FOOD = Path(args[0]).resolve() if args else ROOT / "food"
PJ, KNOWN = ROOT / "photos.json", ROOT / "photo_urls.json"
TODAY = dt.datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
BAD = re.compile(r"logo|placeholder|default|favicon|avatar|icon|sprite|blank|gravatar", re.I)

def field(text, name):
    m = re.search(rf"^- \*\*{name}:\*\*\s*(\S+)", text, re.M)
    return m.group(1) if m else ""

def og_image(url):
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    h = r.text[:400000]
    for pat in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, h, re.I)
        if m and not BAD.search(m.group(1)):
            return requests.compat.urljoin(url, m.group(1).replace("&amp;", "&"))
    return None

def save(img_url, slug, referer=None):
    hd = dict(UA); hd["Accept"] = "image/avif,image/webp,image/*,*/*;q=0.8"
    if referer: hd["Referer"] = referer
    r = requests.get(img_url, headers=hd, timeout=20)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    im.load()
    if im.width < 300 or im.height < 200:
        raise ValueError(f"too small {im.size}")
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA"); bg.paste(im, mask=im.split()[-1]); im = bg
    im = im.convert("RGB")
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
    out = ROOT / "photos" / f"{slug}.jpg"
    out.parent.mkdir(exist_ok=True)
    im.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    return f"photos/{slug}.jpg"

def domain(u):
    return re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*", r"\1", u))

def attempt(slug, text, known):
    photo, src = field(text, "Photo"), field(text, "Source")
    rec = {"path": "", "source": "", "credit": "", "status": "unavailable", "checked": TODAY}
    try:
        if photo.startswith("http"):
            rec.update(path=save(photo, slug), source=photo, credit=domain(src) if src.startswith("http") else domain(photo), status="ok")
        elif slug in known:
            k = known[slug]
            rec.update(path=save(k["url"], slug), source=k["url"], credit=k.get("via", domain(k["url"])), status="ok")
        elif re.match(r"https?://(www\.)?(x|twitter)\.com/", src):
            rec.update(status="missing", note="X post: add its media URL to photo_urls.json")
        elif src.startswith("http"):
            img = og_image(src)
            if img:
                rec.update(path=save(img, slug, referer=src), source=img, credit=domain(src), status="ok")
            else:
                rec["note"] = "no og:image on source page"
        else:
            rec["note"] = "no photo or web source on card"
    except Exception as e:  # one quick attempt only
        rec["note"] = f"{type(e).__name__}: {str(e)[:120]}"
        if re.search(r"\b(403|429|503)\b", str(e)):  # bot-check/rate-limit: worth a later try
            rec["status"] = "missing"; rec["note"] = "site bot-check blocked the page (" + rec["note"][:60] + ")"
    return slug, rec

def main():
    data = json.loads(PJ.read_text()) if PJ.exists() else {}
    known = {k: v for k, v in (json.loads(KNOWN.read_text()) if KNOWN.exists() else {}).items() if not k.startswith("_")}
    todo = []
    for f in sorted((FOOD / "recipes").glob("*.md")):
        slug, cur = f.stem, data.get(f.stem)
        if cur and cur.get("status") == "ok" and (ROOT / cur.get("path", "-")).exists():
            continue
        if cur and cur.get("status") == "unavailable" and not RETRY:
            continue
        if cur and cur.get("status") == "missing" and cur.get("note", "").startswith("X post") and slug not in known:
            continue  # nothing new to try until a media URL is added
        if cur and cur.get("status") == "missing" and not RETRY and slug not in known:
            age = (dt.date.fromisoformat(TODAY) - dt.date.fromisoformat(cur.get("checked", "2000-01-01"))).days
            if age < 7:
                continue  # blocked recently; one quick try per week at most
        todo.append((slug, f.read_text(encoding="utf-8")))
    with ThreadPoolExecutor(8) as ex:
        for slug, rec in ex.map(lambda a: attempt(a[0], a[1], known), todo):
            data[slug] = rec
            print(f"{rec['status']:12} {slug}  {rec.get('note', '')}")
    data = dict(sorted(data.items()))
    PJ.write_text(json.dumps(data, indent=1) + "\n")
    st = [v["status"] for v in data.values()]
    print(f"tried {len(todo)}; ok {st.count('ok')}, missing {st.count('missing')}, unavailable {st.count('unavailable')}")

if __name__ == "__main__":
    main()
