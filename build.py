#!/usr/bin/env python3
"""Build the Kitchen recipe library from food/recipes/*.md.

Usage: python3 build.py [path/to/food]      (default: ./food)

Reads <food>/recipes/*.md and photos.json (written by fetch_photos.py) and writes
index.html, recipes/<slug>/index.html, week/index.html (This Week + archive), robots.txt, .nojekyll.
Privacy: family names, private notes and private vault paths are stripped HERE, at
render time. The source markdown is never modified.
"""
import html
import json
import re
import sys
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent
FOOD = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "food"
RECIPES = FOOD / "recipes"
SITE_URL = "https://vnqqsmhyvm-a11y.github.io/kitchen/"
esc = html.escape

# ---------------------------------------------------------------- privacy
NAMES = r"\b(?:Max|Allison|Vera|Penny|Jax|Maggie|Jamison|Leach)\b"
DROP_ABOUT = {"approved by", "disliked by", "last made", "photo", "source", "health flags"}
# Lines to drop entirely (personal preferences, private queue notes).
DROP_LINE = [
    r"queued-recipes", r"standing (?:steak )?favorite", r"grilled-meat preference",
    r"\blikes this one\b",
]
# Ordered (pattern, replacement) rewrites. Applied per line.
REWRITES = [
    (r"; use the fallback in family-preferences\.md", "; plan a simple fish-free fallback"),
    (r"Vera \(fish\) — do not serve this dish to her", "Contains fish or shellfish — not for a fish-allergic eater"),
    (r"Vera's fallback(?: \(age \d+\))?", "Fish-free fallback"),
    (r"Make Vera's pack", "Make the fish-free pack"),
    (r"Vera's pack", "Fish-free pack"),
    (r"Vera \(fish allergy\) method change", "Fish-free method change"),
    (r"Vera \(fish allergy\)", "Fish-free swap"),
    (r"Method tweak for Vera", "Fish-free method tweak"),
    (r"Vera note", "Fish-allergy note"),
    (r"House change — Vera", "House change — fish-free"),
    (r"Vera-safe", "Fish-allergy safe"),
    (r"Vera swap", "fish-free swap"),
    (r"Still a fish-night for Vera\.", "Still counts as a fish night (fish-free fallback below)."),
    (r"so Vera's portion of the base is fish-free", "so the base stays fish-free"),
    (r"^Vera's grilled steak favorite", "A family grilled-steak favorite"),
    (r"her proven fallback", "the proven fallback"),
    (r"Mix hers\b", "Mix the fish-free pack"),
    (r"to hers\.", "to the fish-free portion."),
    (r'write "V"', 'write "FF"'),
    (r"\bVera first\b", "Fish-free plate first"),
    (r"\bVera gets\b", "The fish-free plate gets"),
    (r"\bshe gets\b", "the fish-free plate gets"), (r"\bShe gets\b", "The fish-free plate gets"),
    (r"(?:\b|^)Vera's (?=\w)", "VERAPOSS "),
    (r"\bfor Vera\b", "for the fish-allergic eater"),
    (r"Always a hit EXCEPT Penny & Vera \([^)]*\) — consider a plain protein for the girls\.",
     "Usually a hit — keep a plain protein on hand for picky eaters."),
    (r"\s*\(Maggie away/suspected no\)", ""),
    # Max
    (r"The family build — captured from Max, ", "The family build, "),
    (r"; Max still dialing in time/temp", "; still dialing in time/temp"),
    (r"\s*Captured \d{4}-\d\d-\d\d from Max's link\.", ""),
    (r"from Max's Taste of Home link", "from a Taste of Home link"),
    (r"2 for Max/Jax/anyone hungry", "2 for anyone hungry"),
    (r"Simplified from the source at Max's request:", "Simplified from the source:"),
    (r"Max is at the oven anyway", "You're at the oven anyway"),
    (r"recipe (photo|card) shared by Max", r"family recipe \1"),
    (r"at the table for Max", "at the table for the adults"),
    (r"^Max's build, ", "House build, "),
    (r"they double as Max's snack nuts", "they double as snack nuts"),
    (r"— Max's idea:", "— a house idea:"),
    (r"seconds for Max/Jax or a lunch", "seconds or a lunch"),
    # private vault paths / jargon
    (r"the old Meals\.md rotation", "the old meal rotation"),
    (r"by the diet-lens test", "by the house Mediterranean test"),
    (r"diet-lens", "house diet"),
]

def _poss(m_text):
    return m_text

def scrub(line, had_vera=None):
    """Return the privacy-scrubbed line, or None to drop it."""
    for p in DROP_LINE:
        if re.search(p, line):
            return None
    vera = "Vera" in line
    for p, r in REWRITES:
        line = re.sub(p, r, line)
    if vera:
        # possessive "Vera's X" -> "the fish-free X" (capitalised at a sentence/bold start)
        line = re.sub(r"(^|\*\*|[.!?:]\s+|^\d+\.\s+|^-\s+)VERAPOSS ", lambda m: m.group(1) + "The fish-free ", line)
        line = line.replace("VERAPOSS ", "the fish-free ")
        line = re.sub(r"\bto her\b", "to that plate", line)
        line = re.sub(r"\bher\b", "the fish-free", line)
        line = re.sub(r"\bHer\b", "The fish-free", line)
        line = re.sub(r"\bVera\b", "a fish-free plate", line)
    if re.search(NAMES, line):
        return None  # safety net: never publish a family name
    if re.search(r"\b[\w-]+\.md\b", re.sub(r"\]\([a-z0-9-]+\.md(?:#[\w-]*)?\)", "]()", line)):
        return None  # leftover private vault path
    return line

# ---------------------------------------------------------------- parsing
def parse(path):
    raw = path.read_text(encoding="utf-8").splitlines()
    slug = path.stem
    title, sections, cur = slug.replace("-", " ").title(), [], None
    for ln in raw:
        if ln.startswith("# ") and cur is None and not sections:
            title = ln[2:].strip(); continue
        if ln.startswith("## "):
            cur = {"name": ln[3:].strip(), "lines": []}; sections.append(cur); continue
        if cur is None:
            cur = {"name": "", "lines": []}; sections.append(cur)
        cur["lines"].append(ln)
    about, extra_about, intro = {}, [], []
    body_sections = []
    for s in sections:
        if s["name"].lower() == "about":
            for ln in s["lines"]:
                m = re.match(r"^- \*\*([^*]+?):\*\*\s*(.*)$", ln)
                if m:
                    key, val = m.group(1).strip(), m.group(2).strip()
                    std = key.lower()
                    if std in ("meal", "serves", "protein", "cook", "ww tier", "mediterranean",
                               "make-ahead / leftovers", "status", "source", "photo", "allergy",
                               "approved by", "disliked by", "last made", "health flags"):
                        about[std] = val
                    else:
                        extra_about.append(ln)
                elif ln.strip():
                    intro.append(ln)
                elif intro and intro[-1] != "":
                    intro.append("")
        else:
            body_sections.append(s)
    return {"slug": slug, "title": title, "about": about, "extra": extra_about,
            "intro": intro, "sections": body_sections}

def minutes(text):
    """Parse '1 hr 45 min' / '3.5 hr' / '40 min' into minutes."""
    t = 0.0; found = False
    for n, u in re.findall(r"(\d+(?:\.\d+)?)\s*(hr|hour|min)", text):
        t += float(n) * (60 if u.startswith("h") else 1); found = True
    return int(t) if found else None

def cook_info(cook):
    m = re.search(r"/\s*([^·/]*?)\s*total", cook or "")
    total = minutes(m.group(1)) if m else None
    method = (cook or "").split("·")[0].strip()
    effort = (cook or "").split("·")[-1].strip().lower() if "·" in (cook or "") else ""
    return method, total, effort

PROTEINS = ["chicken", "beef", "turkey", "pork", "sausage", "ham", "bacon", "fish", "shrimp", "egg", "tofu"]
LEGUME_WORDS = r"\b(legume|beans?|lentils?|chickpeas?|split peas|black-eyed|falafel|hummus|chana|dal)\b"

def tags_for(r):
    a = r["about"]
    tags = []  # (group, value, label)
    meal = (a.get("meal") or "").split()[0].lower() if a.get("meal") else ""
    if meal:
        tags.append(("meal", meal, meal.capitalize()))
    prot = (a.get("protein") or "").lower()
    seen = set()
    for p in PROTEINS:
        if re.search(rf"\b{p}", prot) and not re.search(rf"{p} optional", prot):
            v = {"ham": "pork", "bacon": "pork", "tofu": "vegetarian"}.get(p, p)
            if p == "bacon" and "garnish" in prot:
                continue
            if v not in seen:
                seen.add(v); tags.append(("protein", v, v.capitalize()))
    if "vegetarian" in prot and "vegetarian" not in seen:
        seen.add("vegetarian"); tags.append(("protein", "vegetarian", "Vegetarian"))
    if prot.startswith("none") and not seen:
        tags.append(("protein", "none", "No meat"))
    title = r["title"].lower(); slug = r["slug"]
    if re.search(LEGUME_WORDS, prot) or re.search(LEGUME_WORDS, title) or re.search(LEGUME_WORDS, slug.replace("-", " ")):
        tags.append(("protein", "legume", "Legume"))
    if re.search(r"\b(fish|shrimp|salmon|tuna|cod|tilapia|seafood|shellfish)\b", prot):
        tags.append(("x", "fish", "Fish & seafood"))
    med = (a.get("mediterranean") or "").lower()
    if med.startswith("yes"):
        tags.append(("med", "yes", "Mediterranean"))
    elif med:
        tags.append(("med", "no", "Not Mediterranean"))
    _, total, effort = cook_info(a.get("cook"))
    cook = (a.get("cook") or "").lower()
    if (total is not None and total <= 30) or "quick" in cook:
        tags.append(("effort", "quick", "Quick ≤30 min"))
    if "easy" in effort or "easy" in cook:
        tags.append(("effort", "easy", "Easy"))
    st = (a.get("status") or "").split()[0].lower() if a.get("status") else ""
    if st:
        label = {"active": "Approved", "approved": "Approved", "probation": "Trying out", "new": "New"}.get(st, st.capitalize())
        val = "approved" if st == "active" else st
        tags.append(("status", val, label))
    # dedupe
    out, s2 = [], set()
    for t in tags:
        if (t[0], t[1]) not in s2:
            s2.add((t[0], t[1])); out.append(t)
    return out

# ---------------------------------------------------------------- markdown (tiny)
def inline(text, slugs, depth):
    base = "../" * depth
    parts = []
    pos = 0
    # protect links first
    def link(m):
        label, target = m.group(1), m.group(2)
        mm = re.fullmatch(r"([a-z0-9-]+)\.md(?:#[\w-]*)?", target)
        if mm and mm.group(1) in slugs:
            return f"\x00a href=\"{base}recipes/{mm.group(1)}/\"\x01{label}\x00/a\x01"
        if re.match(r"https?://", target):
            return f"\x00a href=\"{esc(target, quote=True)}\" rel=\"noopener noreferrer nofollow\"\x01{label}\x00/a\x01"
        return label  # private/unknown target: plain text
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    t = esc(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<span class=\"code\">\1</span>", t)
    t = t.replace("\x00", "<").replace("\x01", ">")
    return t

def render_block(lines, slugs, depth):
    out, i = [], 0
    clean = []
    for ln in lines:
        s = scrub(ln)
        if s is not None:
            clean.append(s)
    lines = clean
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if re.match(r"^\s*[-*] ", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append(re.sub(r"^\s*[-*] ", "", lines[i])); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x, slugs, depth)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\s*\d+[.)] ", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.)] ", lines[i]):
                items.append(re.sub(r"^\s*\d+[.)] ", "", lines[i])); i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x, slugs, depth)}</li>" for x in items) + "</ol>")
            continue
        if ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:], slugs, depth)}</h3>"); i += 1; continue
        if re.fullmatch(r"\*\*[^*]+\*\*:?", ln.strip()):
            out.append(f"<h3 class=\"sub\">{inline(ln.strip().strip('*').rstrip(':').rstrip('*'), slugs, depth)}</h3>"); i += 1; continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*([-*]|\d+[.)]) ", lines[i]) and not lines[i].startswith("#"):
            para.append(lines[i].strip()); i += 1
        if para:
            out.append(f"<p>{inline(' '.join(para), slugs, depth)}</p>")
        else:
            i += 1
    return "\n".join(out)

def plain(text):
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*`_]", "", t)

# ---------------------------------------------------------------- templates
FONT_PRELOAD = "".join(
    f'<link rel="preload" href="{{base}}assets/fonts/{f}" as="font" type="font/woff2" crossorigin>'
    for f in ("source-serif-4-latin-400-normal.woff2", "playfair-display-latin-900-normal.woff2", "oswald-latin-500-normal.woff2"))

def head(title, base, css_v):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f5f0e6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#171512" media="(prefers-color-scheme: dark)">
<title>{esc(title)}</title>
{FONT_PRELOAD.replace('{base}', base)}
<link rel="stylesheet" href="{base}assets/site.css?v={css_v}">
</head>
<body>
<div class="page">"""

def masthead(base, current, count):
    lib = 'aria-current="page"' if current == "lib" else ""
    wk = 'aria-current="page"' if current == "week" else ""
    return f"""<header class="masthead">
<div class="dateline"><span>From our kitchen</span><span>{count} recipes</span></div>
<div class="nameplate"><a href="{base}">The Kitchen</a></div>
<nav class="band" aria-label="Sections"><a href="{base}" {lib}>Recipe Library</a><span class="sep">·</span><a href="{base}week/" {wk}>This Week</a></nav>
</header>"""

FOOT = """<footer class="colophon">Family recipe box · cards adapted from the linked sources · photos from each recipe’s source</footer>
</div>
</body>
</html>
"""

GROUPS = [("meal", "Meal"), ("protein", "Protein"), ("x", "Seafood"), ("med", "Diet"),
          ("effort", "Effort"), ("status", "Status")]
GROUP_ORDER = {
    "meal": ["dinner", "lunch", "breakfast", "side", "snack", "dessert"],
    "protein": ["chicken", "beef", "turkey", "pork", "sausage", "fish", "shrimp", "legume", "egg", "vegetarian", "none"],
    "status": ["approved", "probation", "new"],
}

def placeholder(r, cls="ph"):
    letter = esc(r["title"][:1].upper())
    return f'<div class="{cls}" aria-hidden="true"><span class="ph-l">{letter}</span><span class="ph-t">Photo to come</span></div>'

def card(r, photo, base):
    tags = r["tags"]
    data = " ".join(f"{g}:{v}" for g, v, _ in tags)
    a = r["about"]
    _, total, _ = cook_info(a.get("cook"))
    meta = []
    if a.get("meal"): meta.append(a["meal"].split()[0].capitalize())
    if total: meta.append(f"{total} min" if total < 120 else f"{total/60:g} hr")
    if a.get("serves"): meta.append(f"serves {a['serves'].split()[0]}")
    img = (f'<img src="{base}{esc(photo["path"])}" alt="" loading="lazy" decoding="async">'
           if photo else placeholder(r))
    search = " ".join([r["title"], a.get("protein", ""), " ".join(l for _, _, l in tags), r["ingredients_text"]]).lower()
    shown = [l for g, v, l in tags if g in ("protein", "med") and not (g == "med" and v == "no")][:3]
    return (f'<li class="card" data-tags="{esc(data)}" data-search="{esc(search)}">'
            f'<a href="{base}recipes/{r["slug"]}/"><div class="thumb">{img}</div>'
            f'<div class="cbody"><span class="ck">{esc(" · ".join(meta))}</span>'
            f'<span class="ct">{esc(r["title"])}</span>'
            f'<span class="ctags">{"".join(f"<i>{esc(s)}</i>" for s in shown)}</span></div></a></li>')

def build_home(recs, photos, css_v):
    base = ""
    allv = {}
    for r in recs:
        for g, v, l in r["tags"]:
            allv.setdefault(g, {}).setdefault(v, [l, 0])[1] += 1
    chips = []
    for g, glabel in GROUPS:
        vals = allv.get(g, {})
        order = GROUP_ORDER.get(g, [])
        keys = sorted(vals, key=lambda v: (order.index(v) if v in order else 99, v))
        if not keys: continue
        chips.append(f'<div class="cg"><span class="cgl">{glabel}</span>' + "".join(
            f'<button type="button" class="chip" data-g="{g}" data-v="{esc(v)}" aria-pressed="false">{esc(vals[v][0])} <small>{vals[v][1]}</small></button>'
            for v in keys) + "</div>")
    cards = "\n".join(card(r, photos.get(r["slug"]), base) for r in recs)
    return head("Recipe Library — The Kitchen", base, css_v) + masthead(base, "lib", len(recs)) + f"""
<main class="lib">
<h1 class="sr">Recipe Library</h1>
<div class="finder">
<label class="sr" for="q">Search recipes</label>
<input id="q" type="search" placeholder="Search recipes or ingredients…" autocomplete="off" enterkeyhint="search">
<details class="filters" open><summary>Filters <span id="nsel"></span></summary>
{''.join(chips)}
<button type="button" id="clear" class="clear">Clear all</button>
</details>
<p class="count" id="count" aria-live="polite">{len(recs)} recipes</p>
</div>
<ul class="grid" id="grid">
{cards}
</ul>
<p class="none" id="none" hidden>No recipes match. Try fewer filters.</p>
</main>
<script>
(function(){{
var q=document.getElementById('q'),cards=[].slice.call(document.querySelectorAll('.card')),
chips=[].slice.call(document.querySelectorAll('.chip')),count=document.getElementById('count'),
none=document.getElementById('none'),nsel=document.getElementById('nsel'),sel={{}};
function apply(){{var t=q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean),n=0,k=0;
for(var g in sel)k+=sel[g].length;
cards.forEach(function(c){{var tags=' '+c.dataset.tags+' ',s=c.dataset.search,ok=true;
for(var g in sel){{if(sel[g].length&&!sel[g].some(function(v){{return tags.indexOf(' '+g+':'+v+' ')>-1}}))ok=false}}
if(ok)ok=t.every(function(w){{return s.indexOf(w)>-1}});c.hidden=!ok;if(ok)n++}});
count.textContent=n+' of '+cards.length+' recipes';none.hidden=n>0;nsel.textContent=k?'('+k+')':''}}
chips.forEach(function(b){{b.addEventListener('click',function(){{var g=b.dataset.g,v=b.dataset.v;sel[g]=sel[g]||[];
var i=sel[g].indexOf(v);if(i>-1)sel[g].splice(i,1);else sel[g].push(v);
b.setAttribute('aria-pressed',i>-1?'false':'true');apply()}})}});
document.getElementById('clear').addEventListener('click',function(){{sel={{}};q.value='';
chips.forEach(function(b){{b.setAttribute('aria-pressed','false')}});apply()}});
q.addEventListener('input',apply);
if(window.matchMedia('(max-width:40rem)').matches)document.querySelector('.filters').removeAttribute('open');
}})();
</script>
""" + FOOT

def build_recipe(r, photo, slugs, total_count, css_v):
    base = "../../"
    a = r["about"]
    method_, total, effort = cook_info(a.get("cook"))
    facts = []
    def fact(k, v):
        if v:
            s = scrub(v)
            if s: facts.append(f"<div><dt>{k}</dt><dd>{inline(s, slugs, 2)}</dd></div>")
    fact("Meal", (a.get("meal") or "").capitalize())
    fact("Serves", a.get("serves"))
    fact("Protein", a.get("protein"))
    fact("Cook", a.get("cook"))
    fact("Make-ahead / leftovers", a.get("make-ahead / leftovers"))
    fact("Mediterranean", a.get("mediterranean"))
    fact("WW tier", a.get("ww tier"))
    st = (a.get("status") or "")
    fact("Status", {"active": "Approved (in rotation)", "probation": "Trying out (probation)"}.get(st.split()[0].lower(), st) if st else "")
    allergy = a.get("allergy")
    allergy_html = ""
    if allergy:
        s = scrub(allergy)
        if s: allergy_html = f'<p class="allergy"><strong>Allergy:</strong> {inline(s, slugs, 2)}</p>'
    fig = ""
    if photo:
        cred = photo.get("credit") or ""
        fig = (f'<figure class="hero"><img src="{base}{esc(photo["path"])}" alt="{esc(r["title"])}" decoding="async">'
               + (f'<figcaption>Photo: {esc(cred)}</figcaption>' if cred else "") + "</figure>")
    else:
        fig = f'<figure class="hero">{placeholder(r, "ph big")}</figure>'
    intro = render_block(r["intro"], slugs, 2)
    extra = render_block(r["extra"], slugs, 2)
    secs = []
    ing = meth = ""
    for s in r["sections"]:
        body = render_block(s["lines"], slugs, 2)
        if not body.strip(): continue
        n = s["name"].lower()
        if n == "ingredients": ing = body
        elif n == "method": meth = body
        else: secs.append((s["name"], body))
    cols = ""
    if ing or meth:
        cols = '<div class="cols">' + (f'<section class="ing"><h2 class="kicker">Ingredients</h2>{ing}</section>' if ing else "") \
            + (f'<section class="meth"><h2 class="kicker">Method</h2>{meth}</section>' if meth else "") + "</div>"
    else:
        cols = '<p class="todo">No written recipe on the card yet.</p>'
    others = "".join(f'<section class="more"><h2 class="kicker">{esc(n)}</h2>{b}</section>'
                     for n, b in secs if n.lower() != "notes")
    notes_html = "".join(b for n, b in secs if n.lower() == "notes")
    if extra: notes_html = extra + notes_html
    notes = f'<section class="more notes"><h2 class="kicker">Notes</h2>{notes_html}</section>' if notes_html else ""
    src = a.get("source") or ""
    src_html = ""
    if re.match(r"https?://", src):
        dom = re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*", r"\1", src))
        src_html = f'<p class="src"><a class="btn" href="{esc(src, quote=True)}" rel="noopener noreferrer nofollow" target="_blank">Original recipe at {esc(dom)} ↗</a></p>'
    elif src and scrub(src):
        src_html = f'<p class="src">Source: {esc(plain(scrub(src)))}</p>'
    chips = "".join(f'<i>{esc(l)}</i>' for g, _, l in r["tags"] if g != "x")
    return head(f'{r["title"]} — The Kitchen', base, css_v) + masthead(base, "lib", total_count) + f"""
<main class="recipe">
<p class="back"><a href="{base}">← Recipe Library</a></p>
<article>
<h1>{esc(r["title"])}</h1>
<p class="rtags">{chips}</p>
{fig}
<dl class="facts">{''.join(facts)}</dl>
{allergy_html}
<div class="intro">{intro}</div>
{cols}
{others}
{notes}
{src_html}
</article>
</main>
""" + FOOT

# ---------------------------------------------------------------- week plans

WIKI = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")
DAY_ROW = re.compile(
    r"^\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b[^|]*\|\s*([^|]+)\|",
    re.I,
)
QUEUED_ROW = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*[^|]*\|\s*[^|]*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|",
)

def title_key(s):
    s = scrub(s) or s
    s = re.sub(r"\s+", " ", s.strip().lower())
    return s

def build_title_map(recs):
    """Map scrubbed # title → slug. Also index the part before a parenthetical."""
    m = {}
    for r in recs:
        title = r["title"]
        m[title_key(title)] = r["slug"]
        # "Curry Chicken (Red Curry Chicken & Rice)" also answers [[Curry Chicken]]
        short = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
        if short and title_key(short) not in m:
            m[title_key(short)] = r["slug"]
    return m

def dinner_cell(raw, title_map):
    """Return (display_text, slug_or_None, from_wiki). Wikilink → recipe if known; else plain."""
    raw = raw.strip()
    m = WIKI.search(raw)
    if m:
        name = m.group(1).strip()
        slug = title_map.get(title_key(name))
        display = scrub(name) or name
        if re.search(NAMES, display):
            display = re.sub(NAMES, "", display).strip(" -–—")
        return display, slug, True
    # plain / open night
    text = scrub(raw) or raw
    text = WIKI.sub(lambda mm: mm.group(1), text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    if re.search(NAMES, text):
        text = re.sub(NAMES, "", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" -–—")
    return text.strip(), None, False

def parse_plan(path, title_map):
    """Parse plans/YYYY-MM-DD.md → {sat, mon, days:[(dow, label, text, slug)|...]}."""
    sat = date.fromisoformat(path.stem)
    mon = sat - timedelta(days=5)
    lines = path.read_text(encoding="utf-8").splitlines()
    in_week = False
    days = []  # Mon–Sat only
    seen = set()
    for ln in lines:
        if ln.startswith("## "):
            in_week = ln.strip().lower() == "## the week"
            continue
        if not in_week:
            continue
        if ln.startswith("## "):
            break
        m = DAY_ROW.match(ln)
        if not m:
            continue
        dow = m.group(1).capitalize()
        if dow == "Sun":
            continue
        if dow in seen:
            continue
        seen.add(dow)
        text, slug, from_wiki = dinner_cell(m.group(2), title_map)
        # day label from cell start e.g. "Mon Oct 12"
        day_label = ln.split("|")[1].strip()
        day_label = scrub(day_label) or day_label
        days.append({"dow": dow, "label": day_label, "text": text, "slug": slug, "from_wiki": from_wiki})
    order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    days.sort(key=lambda d: order.index(d["dow"]) if d["dow"] in order else 99)
    return {"sat": sat, "mon": mon, "days": days, "path": path}

def parse_queued(path, title_map, current_sat):
    """Upcoming: status queued, or scheduled for a week after current_sat."""
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("|") or ln.startswith("|---") or ln.startswith("| Recipe"):
            continue
        parts = [p.strip() for p in ln.strip("|").split("|")]
        if len(parts) < 5:
            continue
        recipe, _card, _req, target, status = parts[0], parts[1], parts[2], parts[3], parts[4]
        if recipe.lower() == "recipe":
            continue
        st = status.lower()
        # target week date if present
        tm = re.search(r"(\d{4}-\d{2}-\d{2})", target)
        target_d = date.fromisoformat(tm.group(1)) if tm else None
        upcoming = False
        if st.startswith("queued"):
            upcoming = True
        elif "scheduled" in st:
            if target_d and target_d > current_sat:
                upcoming = True
            elif not target_d:
                upcoming = True
        if not upcoming:
            continue
        # name may be plain or linked
        name = recipe
        wm = WIKI.search(recipe)
        if wm:
            name = wm.group(1).strip()
        name = scrub(name) or name
        if re.search(NAMES, name):
            continue
        slug = title_map.get(title_key(name))
        if not slug:
            cm = re.search(r"recipes/([a-z0-9-]+)\.md", _card)
            if cm and cm.group(1) in set(title_map.values()):
                slug = cm.group(1)
        out.append({"name": name, "slug": slug, "target": target_d, "status": "queued" if st.startswith("queued") else "scheduled"})
    return out

def link_dinner(text, slug, base):
    safe = esc(text)
    if slug:
        return f'<a href="{base}recipes/{esc(slug)}/">{safe}</a>'
    return safe

def render_schedule(days, base, sunday_label="Sunday"):
    rows = []
    for d in days:
        rows.append(
            f'<li><span class="wday">{esc(d["label"])}</span>'
            f'<span class="wdish">{link_dinner(d["text"], d["slug"], base)}</span></li>'
        )
    rows.append(
        f'<li class="emh"><span class="wday">{esc(sunday_label)}</span>'
        f'<span class="wdish">Every man for himself</span></li>'
    )
    return '<ol class="schedule">' + "".join(rows) + "</ol>"

def build_week(recs, title_map, count, css_v):
    base = "../"
    plans_dir = FOOD / "plans"
    today = date.today()  # box clock is America/Chicago
    # Saturday of the Mon–Sat week containing today (Sun → next Sat's week hasn't started; Sun is EMH of prior)
    # Week is Mon–Sat named by its Saturday. If today is Sun, show the week that just ended? Task: current week Saturday is 2026-10-17 on Thu Oct 15.
    # weekday(): Mon=0 … Sun=6. Days until Saturday: (5 - weekday()) % 7 — on Sat = 0.
    wd = today.weekday()
    if wd == 6:  # Sunday EMH — still show the week that ends tomorrow? Or the week that ended yesterday?
        # Sunday is outside Mon–Sat; show the plan whose Sat was yesterday (just-finished week) OR upcoming?
        # Safer: the most recent plan with sat >= today-1 and sat <= today+6, else nearest.
        current_sat = today - timedelta(days=1)  # yesterday was Sat of that week
    else:
        current_sat = today + timedelta(days=(5 - wd))
    # Weekend roll-forward (2026-10-17): Kitchen plans next week on Saturday morning. Once that
    # plan file exists, Sat/Sun show the coming Mon–Sat week; the finishing week moves to Past Weeks.
    if wd in (5, 6):
        nxt = current_sat + timedelta(days=7)
        if (plans_dir / f"{nxt.isoformat()}.md").exists():
            current_sat = nxt

    plans = []
    if plans_dir.is_dir():
        for f in sorted(plans_dir.glob("*.md")):
            if f.name.lower() == "readme.md":
                continue
            try:
                date.fromisoformat(f.stem)
            except ValueError:
                continue
            plans.append(parse_plan(f, title_map))

    current = next((p for p in plans if p["sat"] == current_sat), None)
    if current is None and plans:
        # nearest plan at or after today\'s week, else latest past
        future = [p for p in plans if p["sat"] >= current_sat]
        current = min(future, key=lambda p: p["sat"]) if future else max(plans, key=lambda p: p["sat"])
        current_sat = current["sat"]

    past = sorted([p for p in plans if p["sat"] < current_sat], key=lambda p: p["sat"], reverse=True)
    queued = parse_queued(FOOD / "queued-recipes.md", title_map, current_sat)

    # --- current week block
    if current and current["days"]:
        sun = current["sat"] + timedelta(days=1)
        sun_label = f"Sunday {sun.strftime('%b %-d')}"
        mon_s = current["mon"].strftime("%b %-d")
        sat_s = current["sat"].strftime("%b %-d, %Y")
        week_head = f'<p class="wrange">Monday {esc(mon_s)} – Saturday {esc(sat_s)}</p>'
        sched = render_schedule(current["days"], base, sun_label)
        miss_notes = [d["text"] for d in current["days"] if d.get("from_wiki") and not d["slug"]]
        cur_html = week_head + sched
        if not any(d["slug"] for d in current["days"]) and len(current["days"]) < 6:
            cur_html += '<p class="todo">Plan table incomplete.</p>'
    else:
        cur_html = '<p class="todo">No meal plan on file for this week yet.</p>'
        miss_notes = []

    # --- queued
    q_items = []
    for q in queued:
        name_html = link_dinner(q["name"], q["slug"], base)
        when = q["target"].strftime("%b %-d") if q["target"] else ""
        when_html = f'<span class="qwhen">Week of {esc(when)}</span>' if when else ""
        q_items.append(f"<li>{name_html}{when_html}</li>")
    queued_html = (
        '<ul class="queued">' + "".join(q_items) + "</ul>"
        if q_items else '<p class="todo">Nothing waiting in the queue.</p>'
    )

    # --- archive
    arch = []
    for p in past:
        mon_s = p["mon"].strftime("%b %-d")
        sat_s = p["sat"].strftime("%b %-d, %Y")
        items = "".join(
            f'<li><span class="wday">{esc(d["dow"])}</span>'
            f'<span class="wdish">{link_dinner(d["text"], d["slug"], base)}</span></li>'
            for d in p["days"]
        )
        arch.append(
            f'<details class="arch-week"><summary>Week of {esc(mon_s)} – {esc(sat_s)}</summary>'
            f'<ol class="schedule compact">{items}</ol></details>'
        )
    arch_html = "".join(arch) if arch else '<p class="todo">No past weeks yet.</p>'

    body = head("This Week — The Kitchen", base, css_v) + masthead(base, "week", count) + f"""
<main class="week">
<h1>This Week</h1>
{cur_html}
<h2 class="kicker">Coming Up</h2>
<p class="wlead">Recipes waiting for a future week.</p>
{queued_html}
<h2 class="kicker">Past Weeks</h2>
<div class="archive">
{arch_html}
</div>
</main>
""" + FOOT
    return body, miss_notes, current_sat, current

def main():
    files = sorted(RECIPES.glob("*.md"))
    if not files:
        sys.exit(f"no recipes in {RECIPES}")
    recs = [parse(f) for f in files]
    slugs = {r["slug"] for r in recs}
    for r in recs:
        r["tags"] = tags_for(r)
        ing = next((s for s in r["sections"] if s["name"].lower() == "ingredients"), None)
        r["ingredients_text"] = plain(" ".join(x for x in (scrub(l) for l in (ing["lines"] if ing else [])) if x))[:600]
        r["title"] = scrub(r["title"]) or r["slug"].replace("-", " ").title()
    recs.sort(key=lambda r: r["title"].lower())
    pj = ROOT / "photos.json"
    pdata = json.loads(pj.read_text()) if pj.exists() else {}
    photos = {k: v for k, v in pdata.items()
              if v.get("status") == "ok" and v.get("path") and (ROOT / v["path"]).exists()}
    css = (ROOT / "assets/site.css").read_bytes()
    import hashlib
    css_v = hashlib.sha1(css).hexdigest()[:10]
    (ROOT / "index.html").write_text(build_home(recs, photos, css_v), encoding="utf-8")
    rdir = ROOT / "recipes"
    keep = set()
    for r in recs:
        d = rdir / r["slug"]; d.mkdir(parents=True, exist_ok=True); keep.add(r["slug"])
        (d / "index.html").write_text(build_recipe(r, photos.get(r["slug"]), slugs, len(recs), css_v), encoding="utf-8")
    for d in rdir.iterdir():  # remove pages for deleted recipes
        if d.is_dir() and d.name not in keep:
            for f in d.iterdir(): f.unlink()
            d.rmdir()
    title_map = build_title_map(recs)
    (ROOT / "week").mkdir(exist_ok=True)
    week_html, miss_notes, cur_sat, cur_plan = build_week(recs, title_map, len(recs), css_v)
    (ROOT / "week/index.html").write_text(week_html, encoding="utf-8")
    (ROOT / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (ROOT / ".nojekyll").write_text("")
    # privacy self-check on generated HTML (library + week)
    bad = []
    check_files = [ROOT / "index.html", ROOT / "week/index.html", *rdir.glob("*/index.html")]
    # any archive HTML under week/
    check_files.extend(sorted((ROOT / "week").glob("**/index.html")))
    seen_f = set()
    for f in check_files:
        if f in seen_f or not f.exists():
            continue
        seen_f.add(f)
        t = re.sub(r"<script>.*?</script>", "", f.read_text(), flags=re.S)
        for m in re.finditer(NAMES + r"|queued-recipes|family-preferences|diet-lens|Prosvent", t, re.I):
            bad.append(f"{f.relative_to(ROOT)}: {m.group(0)}")
    if bad:
        print("PRIVACY CHECK FAILED:\n" + "\n".join(bad[:40]), file=sys.stderr); sys.exit(1)
    n_plans = len(list((FOOD / "plans").glob("20*.md"))) if (FOOD / "plans").is_dir() else 0
    print(f"built {len(recs)} recipes, {len(photos)} with photos; week sat={cur_sat} plans={n_plans}")
    if miss_notes:
        print("unresolved dinners (no recipe page): " + "; ".join(miss_notes))

if __name__ == "__main__":
    main()
