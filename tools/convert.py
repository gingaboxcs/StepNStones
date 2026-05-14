#!/usr/bin/env python3
"""
Convert the WordPress mirror at /tmp/stepnstones-mirror into a Jekyll site.

Inputs:
  --mirror  /tmp/stepnstones-mirror/stepnstones.jp   (default)
  --out     /Users/ryan/Websites/Audax/StepNStones   (default)

What it does:
  1. rsyncs wp-content/{themes,uploads,cache} into <out>/wp-content
     (skips files > 50 MB so the local repo stays manageable)
  2. Extracts the shared HTML chrome from the homepage (head, header,
     footer, scripts) and writes Jekyll layouts/default.html.
     A second layout, layouts/news_post.html, wraps individual posts.
  3. Walks every page directory (about/, program/, ...) and emits
     _pages/<slug>.html with front matter and the cleaned content body.
  4. Walks every numeric news-ja/<id>/ directory and emits
     _news/<id>.html with title, date, and body extracted from JSON
     (where available) or DOM (fallback).
  5. Rewrites absolute https://stepnstones.jp URLs to root-relative,
     replaces sp-ao.shortpixel.ai CDN URLs with the local /wp-content
     path, and drops WordPress-only scripts (admin bar, wp-embed, CF7).
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, NavigableString

# ---------------------------------------------------------------------------
# Config

PAGE_SLUGS = [
    "about",
    "program",
    "schedule",
    "daily-schedule",
    "introduction",
    "guidance",
    "users-voice",
    "cambridge",
    "after-program",
    "contact",
]

# Files we don't want to keep around (oversized media, theme dev artifacts).
SKIP_FILE_SUFFIXES = (".DS_Store",)
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB

# Scripts/inline JS we strip from rendered HTML.
DROP_SCRIPT_HOSTS = (
    "translate.google.com/translate_a/element.js",
    "wp-embed.min.js",
    "comment-reply.min.js",
    "wp-emoji-release.min.js",
)
DROP_SCRIPT_KEYWORDS = (
    "wpcf7",            # contact form 7 runtime
    "google-recaptcha",
    "clarity.ms",
    "googletagmanager",
)


# ---------------------------------------------------------------------------
# Helpers

SHORTPIXEL_RE = re.compile(
    r"https://sp-ao\.shortpixel\.ai/client/[^/]+/https?://stepnstones\.jp"
)
ABSOLUTE_RE = re.compile(r"https?://stepnstones\.jp")
SRCSET_RE = re.compile(
    r"https://sp-ao\.shortpixel\.ai/client/[^/]+/https?://stepnstones\.jp([^\s,]+)"
)


def rewrite_urls(html: str) -> str:
    """Strip the ShortPixel proxy + absolute origin from the markup."""
    # ShortPixel proxy first (more specific than the absolute-origin regex)
    html = SHORTPIXEL_RE.sub("", html)
    # Absolute origin URLs become root-relative
    html = ABSOLUTE_RE.sub("", html)
    # Permalink "?page_id=NNN" / "?p=NNN" forms — leave for now, all internal
    # navigation in the rendered DOM still uses the pretty URLs (/about/, etc.)
    return html


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_assets(mirror: Path, out: Path) -> None:
    """Copy wp-content into the Jekyll project. Skip oversized files."""
    src_wp = mirror / "wp-content"
    dst_wp = out / "wp-content"
    if not src_wp.exists():
        print(f"[assets] no wp-content at {src_wp}, skipping", file=sys.stderr)
        return
    n_copied = n_skipped = 0
    for src in src_wp.rglob("*"):
        if src.is_dir():
            continue
        if src.name in SKIP_FILE_SUFFIXES:
            continue
        rel = src.relative_to(src_wp)
        dst = dst_wp / rel
        # wget sometimes appends "@ver=..." to filenames; strip that.
        if "@" in dst.name:
            dst = dst.with_name(dst.name.split("@")[0])
        if src.stat().st_size > MAX_FILE_BYTES:
            print(f"[assets] SKIP big {rel} ({src.stat().st_size//1024//1024} MB)")
            n_skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            continue
        shutil.copy2(src, dst)
        n_copied += 1
    print(f"[assets] copied={n_copied} skipped(too_big)={n_skipped}")


def load_soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def soup_to_html(soup) -> str:
    return str(soup)


def clean_scripts(soup: BeautifulSoup) -> None:
    """Strip WP-specific noise scripts and the admin bar."""
    for tag in soup.find_all("script"):
        src = tag.get("src", "") or ""
        text = tag.string or ""
        if any(host in src for host in DROP_SCRIPT_HOSTS):
            tag.decompose()
            continue
        if any(kw in src for kw in DROP_SCRIPT_KEYWORDS):
            tag.decompose()
            continue
        if any(kw in text for kw in DROP_SCRIPT_KEYWORDS):
            tag.decompose()
            continue

    # WordPress admin bar — only appears when logged in, but drop defensively
    for sel in ("#wpadminbar",):
        node = soup.select_one(sel)
        if node:
            node.decompose()

    # WP comments
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()


# ---------------------------------------------------------------------------
# Layout extraction

def build_default_layout(home: Path, layout_path: Path) -> None:
    """Use the homepage as the template — replace #content with {{ content }}.

    #main_visual and #post_slider are home-only and get stripped from the
    shared layout (they live in the index.html content instead).
    """
    soup = load_soup(home)
    clean_scripts(soup)

    # Drop home-only sections from the layout
    for sel in ("#main_visual", "#post_slider"):
        node = soup.select_one(sel)
        if node:
            node.decompose()

    content = soup.select_one("#content")
    if content is None:
        raise SystemExit("could not find #content in homepage")
    placeholder = soup.new_string("__JEKYLL_CONTENT__")
    content.replace_with(placeholder)

    # Set <html lang> from front matter so we can override later.
    html = soup.find("html")
    if html:
        html["lang"] = "{{ page.lang | default: site.lang }}"

    # Set <title> from front matter.
    title = soup.find("title")
    if title:
        title.string = (
            "{% if page.title and page.title != '' %}"
            "{{ page.title }} – {{ site.title }}"
            "{% else %}"
            "{{ site.title }} – {{ site.description }}"
            "{% endif %}"
        )

    # Drop the ShortPixel preconnect — we no longer route through that CDN.
    for link in soup.find_all("link", rel="preconnect"):
        if "shortpixel" in (link.get("href") or ""):
            link.decompose()

    # Drop Google Translate preconnect — keep the widget but no need to
    # preconnect to its own DNS records since the widget loads on demand.

    markup = soup_to_html(soup)
    markup = rewrite_urls(markup)
    markup = markup.replace("__JEKYLL_CONTENT__", "{{ content }}")

    # Front matter for the layout
    layout = "---\n---\n" + markup + "\n"
    write_text(layout_path, layout)


def build_page_layout(out_layout_path: Path) -> None:
    """Pages just inherit default — their content already includes the
    article/section markup from the original page body."""
    write_text(
        out_layout_path,
        "---\nlayout: default\n---\n{{ content }}\n",
    )


def build_news_post_layout(sample_post_html: Path, layout_path: Path) -> None:
    """Wrap individual posts with the breadcrumb + article shell from one
    of the scraped post pages, leaving title/date/body as Liquid."""
    soup = load_soup(sample_post_html)
    clean_scripts(soup)

    content = soup.select_one("#content")
    if content is None:
        raise SystemExit(f"could not find #content in {sample_post_html}")

    # Replace title text
    h1 = content.select_one(".c-postTitle__ttl")
    if h1:
        h1.clear()
        h1.append(NavigableString("{{ page.title }}"))

    # Replace date markup — keep the structure, swap values
    date_el = content.select_one(".c-postTitle__date")
    if date_el:
        date_el["datetime"] = "{{ page.date | date: '%Y-%m-%d' }}"
        y = date_el.select_one(".__y")
        md = date_el.select_one(".__md")
        if y:
            y.string = "{{ page.date | date: '%Y' }}"
        if md:
            md.string = "{{ page.date | date: '%-m/%-d' }}"

    # Replace post_content with {{ content }}
    body = content.select_one(".post_content")
    if body:
        body.clear()
        body.append(NavigableString("__JEKYLL_CONTENT__"))

    # Strip prev/next nav — Jekyll will inject if/when needed
    nav = content.select_one("#after_article")
    if nav:
        nav.decompose()

    markup = str(content)
    markup = rewrite_urls(markup)
    markup = markup.replace("__JEKYLL_CONTENT__", "{{ content }}")
    write_text(layout_path, "---\nlayout: default\n---\n" + markup + "\n")


# ---------------------------------------------------------------------------
# Page conversion

def transform_contact_form(soup: BeautifulSoup) -> None:
    """Convert WP Contact Form 7 into a Netlify-compatible form."""
    form = soup.select_one("form.wpcf7-form")
    if form is None:
        return
    form["data-netlify"] = "true"
    form["data-netlify-honeypot"] = "bot-field"
    form["name"] = "contact"
    form["action"] = "/contact/?sent=1"
    form["method"] = "POST"
    # Drop CF7-internal hidden fields
    for inp in form.select("input[name^='_wpcf7']"):
        inp.decompose()
    # CF7's success/error message containers — leave the markup, just clear text
    for div in form.select(".wpcf7-response-output"):
        div.decompose()
    # Add Netlify form-name + honeypot
    hidden = soup.new_tag("input", attrs={"type": "hidden", "name": "form-name", "value": "contact"})
    form.insert(0, hidden)
    honeypot = soup.new_tag("p", attrs={"hidden": "", "style": "display:none"})
    honeypot.string = ""
    label = soup.new_tag("label")
    label.string = "Do not fill: "
    bot = soup.new_tag("input", attrs={"name": "bot-field"})
    label.append(bot)
    honeypot.append(label)
    form.insert(1, honeypot)


def extract_main_content(path: Path, *, contact: bool = False) -> str:
    """Pull everything between the (fixed) header and the footer: the
    page-title banner, the breadcrumb, and #content (which wraps
    #main_content).  Inner pages render those three blocks; the homepage
    is built by convert_home() instead."""
    soup = load_soup(path)
    clean_scripts(soup)
    if contact:
        transform_contact_form(soup)

    pieces = []
    for sel in (".l-topTitleArea", ".p-breadcrumb", "#content"):
        node = soup.select_one(sel)
        if node is not None:
            pieces.append(str(node))
    if not pieces:
        # Fallback: just #main_content
        m = soup.select_one("#main_content")
        if m is not None:
            pieces.append(str(m))
    return rewrite_urls("\n".join(pieces))


def convert_pages(mirror: Path, out: Path) -> None:
    for slug in PAGE_SLUGS:
        src = mirror / slug / "index.html"
        if not src.exists():
            print(f"[pages] missing {slug}/", file=sys.stderr)
            continue
        body = extract_main_content(src, contact=(slug == "contact"))
        # Title from <title> tag in source
        soup = load_soup(src)
        raw_title = soup.find("title")
        title = ""
        if raw_title and raw_title.string:
            # WP titles are "Page Name - Site Name"
            title = raw_title.string.split("–")[0].split("-")[0].strip()
        front = (
            "---\n"
            f"layout: page\n"
            f"title: \"{title}\"\n"
            f"permalink: /{slug}/\n"
            "---\n"
        )
        write_text(out / "_pages" / f"{slug}.html", front + body + "\n")
    print(f"[pages] wrote {len(PAGE_SLUGS)} pages")


# ---------------------------------------------------------------------------
# News conversion

def list_news_posts(mirror: Path):
    base = mirror / "news-ja"
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        if not d.name.isdigit():
            continue
        idx = d / "index.html"
        if not idx.exists():
            continue
        yield d.name, idx


def post_metadata(mirror: Path, post_id: str, html_path: Path):
    """Prefer wp-json metadata; fall back to scraping HTML for title/date."""
    json_path = mirror / "wp-json" / "wp" / "v2" / "posts" / post_id
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return {
                "title": BeautifulSoup(
                    data["title"]["rendered"], "html.parser"
                ).get_text().strip(),
                "date": data["date"][:19],
                "slug": data.get("slug", post_id),
            }
        except Exception:
            pass

    soup = load_soup(html_path)
    title_el = soup.select_one(".c-postTitle__ttl")
    title = title_el.get_text(strip=True) if title_el else f"Post {post_id}"
    date_el = soup.select_one(".c-postTitle__date")
    date = ""
    if date_el and date_el.get("datetime"):
        date = date_el["datetime"]
    return {"title": title, "date": date, "slug": post_id}


def extract_post_body(html_path: Path) -> str:
    soup = load_soup(html_path)
    clean_scripts(soup)
    body = soup.select_one(".post_content")
    if body is None:
        return ""
    return rewrite_urls(str(body)).replace("<div class=\"post_content\">", "").rstrip("</div>")


def convert_news(mirror: Path, out: Path) -> None:
    n = 0
    skipped = []
    for post_id, html_path in list_news_posts(mirror):
        meta = post_metadata(mirror, post_id, html_path)
        body = extract_post_body(html_path)
        if not body.strip():
            skipped.append(post_id)
            continue
        # Front matter must escape quotes in titles
        title_safe = meta["title"].replace('"', '\\"')
        date = meta["date"] or "1970-01-01T00:00:00"
        front = (
            "---\n"
            f"layout: news_post\n"
            f"title: \"{title_safe}\"\n"
            f"date: {date}\n"
            f"post_id: {post_id}\n"
            "---\n"
        )
        write_text(out / "_news" / f"{post_id}.html", front + body + "\n")
        n += 1
    print(f"[news] wrote {n} posts; skipped {len(skipped)} empty")


# ---------------------------------------------------------------------------
# Homepage

def convert_home(mirror: Path, out: Path) -> None:
    """Special case: index.html. The homepage uses Swell's mainvisual + post
    slider, then the standard #content wrapper around #main_content."""
    soup = load_soup(mirror / "index.html")
    clean_scripts(soup)
    main_visual = soup.select_one("#main_visual")
    post_slider = soup.select_one("#post_slider")
    content = soup.select_one("#content")

    parts = []
    if main_visual:
        parts.append(str(main_visual))
    if post_slider:
        parts.append(str(post_slider))
    if content:
        parts.append(str(content))
    html = rewrite_urls("\n".join(parts))
    front = "---\nlayout: home\ntitle: \"\"\npermalink: /\n---\n"
    write_text(out / "index.html", front + html + "\n")


def build_home_layout(out: Path) -> None:
    """Home layout = default layout (already includes header/footer)."""
    write_text(
        out / "_layouts" / "home.html",
        "---\nlayout: default\n---\n{{ content }}\n",
    )


# ---------------------------------------------------------------------------
# Entry point

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", default="/tmp/stepnstones-mirror/stepnstones.jp")
    ap.add_argument("--out", default="/Users/ryan/Websites/Audax/StepNStones")
    ap.add_argument("--skip-assets", action="store_true")
    args = ap.parse_args()

    mirror = Path(args.mirror)
    out = Path(args.out)
    if not mirror.exists():
        sys.exit(f"mirror not found: {mirror}")
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_assets:
        copy_assets(mirror, out)

    # Layouts
    print("[layouts] building default layout")
    build_default_layout(mirror / "index.html", out / "_layouts" / "default.html")
    build_page_layout(out / "_layouts" / "page.html")
    build_home_layout(out)

    # Find a "real" news post to use as the news layout template — pick the
    # first post that has reasonably long body text.
    sample = None
    for post_id, html_path in list_news_posts(mirror):
        body = extract_post_body(html_path)
        if len(body) > 200:
            sample = html_path
            break
    if sample is None:
        sample = next(list_news_posts(mirror))[1]
    print(f"[layouts] news_post layout based on {sample}")
    build_news_post_layout(sample, out / "_layouts" / "news_post.html")

    convert_home(mirror, out)
    convert_pages(mirror, out)
    convert_news(mirror, out)

    print("done.")


if __name__ == "__main__":
    main()
