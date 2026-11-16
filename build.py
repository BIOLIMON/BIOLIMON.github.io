#!/usr/bin/env python3
"""Builds the portfolio's /portal/ section (home, work, blog, about, RSS) from content/.

    python3 build.py            build the site
    python3 build.py --drafts   also build posts marked `draft: true`

Reads   content/site.json, content/projects.json, content/about.md, content/posts/*.md
Writes  portal/index.html, portal/work/, portal/blog/ (with feed.xml), portal/about/
Styles  live in portal/style.css — edit that by hand; the build never touches it.

Standard library only (Python 3.8+).
"""
import datetime
import email.utils
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
OUT = ROOT / "portal"
DRAFTS = "--drafts" in sys.argv

SITE = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
SITE_URL = SITE["url"].rstrip("/")
e = html.escape


# ── a small Markdown converter (headings, paragraphs, lists, quotes, code, images, links) ──────────

def slugify(text):
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def safe_url(url):
    """Only http(s), mailto and relative URLs get through; `javascript:` and friends become '#'."""
    url = url.strip().replace('"', "%22")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url) and not re.match(r"^(https?:|mailto:)", url, re.I):
        return "#"
    return url


def inline(text):
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`\n]+)`", stash, text)
    text = html.escape(text, quote=False)            # everything the author types is escaped

    def image(m):
        alt = m.group(1).replace('"', "&quot;")
        return '<img src="%s" alt="%s" loading="lazy">' % (safe_url(m.group(2)), alt)

    def link(m):
        url = safe_url(m.group(2))
        ext = ' target="_blank" rel="noopener"' if re.match(r"^https?:", url, re.I) else ""
        return '<a href="%s"%s>%s</a>' % (url, ext, m.group(1))

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % html.escape(codes[int(m.group(1))], quote=False), text)


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")
HR_RE = re.compile(r"^(\*{3,}|-{3,}|_{3,})\s*$")
FIGURE_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)\s*$')


def starts_block(line):
    return bool(re.match(r"^(```|#{1,6}\s|>)", line) or LIST_RE.match(line) or HR_RE.match(line))


def markdown(src):
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S).replace("\r\n", "\n")   # HTML comments are notes for the author
    lines = src.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = re.match(r"^```\s*([\w+-]*)\s*$", line)                         # fenced code
        if m:
            buf, i = [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = ' class="language-%s"' % m.group(1) if m.group(1) else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, html.escape("\n".join(buf))))
            continue

        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)                    # headings (a lone # is shown as h2)
        if m:
            level = max(2, len(m.group(1)))
            body = inline(m.group(2))
            hid = slugify(body)
            anchor = ' <a class="anchor" href="#%s" aria-label="Link to this section">#</a>' % hid if level <= 3 else ""
            out.append('<h%d id="%s">%s%s</h%d>' % (level, hid, body, anchor, level))
            i += 1
            continue

        if HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith(">"):                                             # block quote
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % markdown("\n".join(buf)))
            continue

        m = LIST_RE.match(line)                                              # lists (one level)
        if m:
            ordered = m.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                cur = lines[i]
                mm = LIST_RE.match(cur)
                if mm and mm.group(2)[0].isdigit() == ordered:
                    items.append(mm.group(3))
                    i += 1
                elif not cur.strip():
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    nxt = LIST_RE.match(lines[j]) if j < len(lines) else None
                    if nxt and nxt.group(2)[0].isdigit() == ordered:
                        i = j
                    else:
                        break
                elif cur.startswith((" ", "\t")) and items:
                    items[-1] += " " + cur.strip()
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(t) for t in items), tag))
            continue

        m = FIGURE_RE.match(line)                                            # an image on its own line
        if m:
            cap = '<figcaption>%s</figcaption>' % inline(m.group(3)) if m.group(3) else ""
            out.append('<figure><img src="%s" alt="%s" loading="lazy">%s</figure>'
                       % (safe_url(m.group(2)), m.group(1).replace('"', "&quot;"), cap))
            i += 1
            continue

        buf = [line]                                                         # paragraph
        i += 1
        while i < len(lines) and lines[i].strip() and not starts_block(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(s.strip() for s in buf)))
    return "\n".join(out)


# ── content ─────────────────────────────────────────────────────────────────────────────────────

def fmt_date(d):
    return "%d %s %d" % (d.day, d.strftime("%b"), d.year)


def load_posts():
    posts, seen = [], set()
    for path in sorted((CONTENT / "posts").glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
        if not m:
            raise SystemExit("%s: a post must start with a front matter block (--- ... ---)" % path.name)
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip().lower()] = v.strip()
        name = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", path.stem)
        date_text = meta.get("date") or (name.group(1) if name else "")
        try:
            date = datetime.date.fromisoformat(date_text)
        except ValueError:
            raise SystemExit("%s: give the post a date, e.g. `date: 2026-11-16`" % path.name)
        slug = meta.get("slug") or (name.group(2) if name else path.stem)
        if slug in seen:
            raise SystemExit("%s: another post already uses the slug '%s'" % (path.name, slug))
        seen.add(slug)
        if meta.get("draft", "").lower() in ("true", "yes", "1") and not DRAFTS:
            continue
        body = m.group(2)
        posts.append({
            "slug": slug,
            "title": meta.get("title") or slug.replace("-", " ").title(),
            "date": date,
            "summary": meta.get("summary", ""),
            "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
            "html": markdown(body),
            "minutes": max(1, math.ceil(len(re.findall(r"\w+", body)) / 200)),
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ── page pieces ─────────────────────────────────────────────────────────────────────────────────

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' rx='6' fill='%230d0d0f'/%3E%3Crect x='9' y='9' width='14' height='14' fill='%23e8b830'/%3E%3C/svg%3E")


def tag_list(tags):
    if not tags:
        return ""
    return '<ul class="tags">%s</ul>' % "".join('<li class="tag">%s</li>' % e(t) for t in tags)


def ext(url):
    return ' target="_blank" rel="noopener"' if url.startswith("http") else ""


def social():
    return '<ul class="social">%s</ul>' % "".join(
        '<li><a href="%s"%s>%s</a></li>' % (e(l["url"]), ext(l["url"]), e(l["label"])) for l in SITE["links"])


def card(p):
    main = p.get("url") or p.get("repo") or "#"
    links = []
    if p.get("url"):
        links.append('<a href="%s"%s>Live site ↗</a>' % (e(p["url"]), ext(p["url"])))
    if p.get("repo"):
        links.append('<a href="%s"%s>Code ↗</a>' % (e(p["repo"]), ext(p["repo"])))
    thumb, cls = "", "card"
    t = p.get("thumb")
    if t and t.get("type") == "roots":                         # an animated ASCII root as the project's picture
        cls += " has-thumb"
        thumb = ('<a class="thumb" href="%s"%s tabindex="-1" aria-hidden="true">'
                 '<div class="roots" data-roots data-seed="%d" data-branch="%s"></div></a>'
                 ) % (e(main), ext(main), int(t.get("seed", 3)), float(t.get("branch", 0.1)))
    return (
        '<article class="%s">%s<div class="card-body">'
        '<div class="card-top"><span>%s</span></div>'
        '<h3><a href="%s"%s>%s</a></h3>'
        '<p>%s</p>%s'
        '<p class="card-links">%s</p>'
        '</div></article>'
    ) % (cls, thumb, e(str(p.get("year", ""))), e(main), ext(main), e(p["title"]), e(p["summary"]),
         tag_list(p.get("tags", [])), " ".join(links))


def post_row(p, up):
    summary = "<p>%s</p>" % e(p["summary"]) if p["summary"] else ""
    return (
        '<li class="post-row"><time datetime="%s">%s</time><div>'
        '<h3><a href="%sblog/%s/">%s</a></h3>%s%s</div></li>'
    ) % (p["date"].isoformat(), fmt_date(p["date"]), up, e(p["slug"]), e(p["title"]), summary, tag_list(p["tags"]))


def layout(*, title, desc, depth, body, active="", url_path="", og_type="website", arrive=False, scripts=False):
    up = "../" * depth
    nav = "".join(
        '<a href="%s%s/"%s>%s</a>' % (up, key, ' aria-current="page"' if key == active else "", label)
        for key, label in (("work", "Work"), ("blog", "Blog"), ("about", "About")))
    page_url = "%s/portal/%s" % (SITE_URL, url_path)
    full_title = "%s — %s" % (title, SITE["name"]) if title else "%s — %s" % (SITE["name"], "portfolio & blog")
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="color-scheme" content="dark light">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="{name}">
<meta name="twitter:card" content="summary">
<link rel="canonical" href="{url}">
<link rel="icon" href="{icon}">
<link rel="alternate" type="application/rss+xml" title="{name} — blog" href="{up}blog/feed.xml">
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
{arrive}<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="{up}"><span class="mark" aria-hidden="true"></span>{name}</a>
    <nav class="site-nav" aria-label="Main">{nav}</nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap">
    <p>© {year} {full_name}</p>
    <ul>
      <li><a href="{up}blog/feed.xml">RSS</a></li>
      <li><a href="{up}../">← The curtain</a></li>
    </ul>
  </div>
</footer>
{scripts}</body>
</html>
""".format(
        title=e(full_title), desc=e(desc), og_type=og_type, url=e(page_url), name=e(SITE["name"]),
        full_name=e(SITE["full_name"]), icon=ICON, up=up, nav=nav, body=body, year=datetime.date.today().year,
        arrive='<div id="arrive" aria-hidden="true"></div>\n' if arrive else "",
        scripts=('<script src="%sroots.js" defer></script>\n' % up) if scripts else "")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("  wrote", path.relative_to(ROOT))


# ── pages ───────────────────────────────────────────────────────────────────────────────────────

def build():
    projects = json.loads((CONTENT / "projects.json").read_text(encoding="utf-8"))
    posts = load_posts()
    about_html = markdown((CONTENT / "about.md").read_text(encoding="utf-8"))

    for sub in ("work", "blog", "about"):                                    # regenerate from scratch; style.css is left alone
        shutil.rmtree(OUT / sub, ignore_errors=True)

    # home
    featured = [p for p in projects if p.get("featured")] or projects[:3]
    latest = ('<ul class="posts">%s</ul>' % "".join(post_row(p, "") for p in posts[:3])) if posts \
        else '<p class="empty">The first post is on its way.</p>'
    home = """<section class="wrap hero">
  <p class="eyebrow">{eyebrow}</p>
  <h1>{headline}</h1>
  <p class="lead">{tagline}</p>
  <p class="cta"><a class="btn" href="work/">See my work</a><a class="btn ghost" href="blog/">Read the blog</a></p>
  {social}
</section>
<section class="wrap section" aria-labelledby="work-h">
  <div class="section-head"><h2 id="work-h">Selected work</h2><a href="work/">All work →</a></div>
  <div class="grid">{cards}</div>
</section>
<section class="wrap section" aria-labelledby="blog-h">
  <div class="section-head"><h2 id="blog-h">Latest writing</h2><a href="blog/">All posts →</a></div>
  {latest}
</section>""".format(
        eyebrow=e(SITE["eyebrow"]), headline=e(SITE["headline"]), tagline=e(SITE["tagline"]), social=social(),
        cards="".join(card(p) for p in featured), latest=latest)
    write(OUT / "index.html", layout(title="", desc=SITE["description"], depth=0, body=home, arrive=True,
                                     scripts=any(p.get("thumb") for p in featured)))

    # work
    work = """<section class="wrap page-head">
  <p class="eyebrow">Work</p>
  <h1>Things I've built</h1>
  <p class="lead">Science, data tools and a bit of art. The code for most of it is open on GitHub.</p>
</section>
<section class="wrap section"><div class="grid">{cards}</div></section>""".format(cards="".join(card(p) for p in projects))
    write(OUT / "work" / "index.html", layout(
        title="Work", desc="Selected projects by %s: bioinformatics, data tools and generative art." % SITE["full_name"],
        depth=1, body=work, active="work", url_path="work/", scripts=any(p.get("thumb") for p in projects)))

    # blog index
    listing = ('<ul class="posts">%s</ul>' % "".join(post_row(p, "../") for p in posts)) if posts \
        else '<p class="empty">No posts yet — the first one is on its way.</p>'
    blog = """<section class="wrap page-head">
  <p class="eyebrow">Blog</p>
  <h1>Notes &amp; writing</h1>
  <p class="lead">Things I build, the data behind them, and the experiments that don't fit anywhere else.</p>
</section>
<section class="wrap section">{listing}</section>""".format(listing=listing)
    write(OUT / "blog" / "index.html", layout(
        title="Blog", desc="Notes and writing by %s." % SITE["full_name"], depth=1, body=blog, active="blog", url_path="blog/"))

    # posts
    for n, p in enumerate(posts):
        newer = posts[n - 1] if n > 0 else None
        older = posts[n + 1] if n + 1 < len(posts) else None
        nav = '<nav class="post-nav" aria-label="More posts">%s%s</nav>' % (
            '<a class="prev" href="../%s/">← %s</a>' % (e(older["slug"]), e(older["title"])) if older else "<span></span>",
            '<a class="next" href="../%s/">%s →</a>' % (e(newer["slug"]), e(newer["title"])) if newer else "")
        body = """<article class="wrap article">
  <header>
    <p class="eyebrow"><a href="../" style="color:inherit;text-decoration:none">← Blog</a></p>
    <h1>{title}</h1>
    <div class="meta"><time datetime="{iso}">{date}</time><span>{mins} min read</span>{tags}</div>
  </header>
  <div class="prose">
{html}
  </div>
  {nav}
</article>""".format(title=e(p["title"]), iso=p["date"].isoformat(), date=fmt_date(p["date"]), mins=p["minutes"],
                    tags=tag_list(p["tags"]), html=p["html"], nav=nav)
        write(OUT / "blog" / p["slug"] / "index.html", layout(
            title=p["title"], desc=p["summary"] or SITE["description"], depth=2, body=body, active="blog",
            url_path="blog/%s/" % p["slug"], og_type="article"))

    # about
    about = """<article class="wrap article">
  <header>
    <p class="eyebrow">About</p>
    <h1>{name}</h1>
  </header>
  <div class="prose">
{html}
  </div>
  {social}
</article>""".format(name=e(SITE["full_name"]), html=about_html, social=social())
    write(OUT / "about" / "index.html", layout(
        title="About", desc=SITE["description"], depth=1, body=about, active="about", url_path="about/"))

    # RSS
    def rfc822(d):
        return email.utils.format_datetime(datetime.datetime(d.year, d.month, d.day, 12, tzinfo=datetime.timezone.utc))
    items = "".join(
        "<item><title>%s</title><link>%s</link><guid isPermaLink=\"true\">%s</guid><pubDate>%s</pubDate>"
        "<description>%s</description></item>" % (
            xml_escape(p["title"]), "%s/portal/blog/%s/" % (SITE_URL, p["slug"]), "%s/portal/blog/%s/" % (SITE_URL, p["slug"]),
            rfc822(p["date"]), xml_escape(p["summary"])) for p in posts)
    feed = ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            "<title>%s — blog</title><link>%s/portal/blog/</link><description>%s</description><language>en</language>"
            '<atom:link href="%s/portal/blog/feed.xml" rel="self" type="application/rss+xml"/>%s</channel></rss>\n') % (
        xml_escape(SITE["name"]), SITE_URL, xml_escape(SITE["description"]), SITE_URL, items)
    write(OUT / "blog" / "feed.xml", feed)

    print("done: %d project(s), %d post(s)%s" % (len(projects), len(posts), " (drafts included)" if DRAFTS else ""))


if __name__ == "__main__":
    build()
