#!/usr/bin/env python3
"""
Download every wp-content/uploads asset referenced anywhere in the scraped
mirror that is not already present locally.

The original site routes images through https://sp-ao.shortpixel.ai/...
We've already rewritten those references to /wp-content/uploads/..., so we
scan the rewritten Jekyll files (and the raw mirror as a fallback) for the
URL set and download any that are missing.
"""

import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path("/Users/ryan/Websites/Audax/StepNStones")
MIRROR = Path("/tmp/stepnstones-mirror/stepnstones.jp")
ORIGIN = "https://stepnstones.jp"
WP_UPLOADS_RE = re.compile(r"/wp-content/uploads/[\w%./@\-]+?\.(?:jpg|jpeg|png|webp|gif|svg|pdf|mp4|mov)", re.IGNORECASE)
SHORTPIXEL_RE = re.compile(r"https://sp-ao\.shortpixel\.ai/client/[^/]+/https?://stepnstones\.jp(/wp-content/uploads/[\w%./@\-]+?\.(?:jpg|jpeg|png|webp|gif|svg|pdf|mp4|mov))", re.IGNORECASE)

# Max-size cap: we skip files larger than 50 MB to avoid pulling huge videos
# into the repo. Existing site's only victim is the 151 MB mp4.
MAX_BYTES = 50 * 1024 * 1024


def collect_urls():
    urls = set()
    # 1. Scan generated Jekyll source (already URL-rewritten)
    for p in ROOT.rglob("*.html"):
        if "_site" in p.parts or "vendor" in p.parts or "wp-content" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in WP_UPLOADS_RE.finditer(txt):
            urls.add(m.group(0))
    # 2. Scan raw mirror HTML for ShortPixel-wrapped URLs to capture anything
    #    that didn't make it through.
    for p in MIRROR.rglob("*.html"):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in SHORTPIXEL_RE.finditer(txt):
            urls.add(m.group(1))
        for m in WP_UPLOADS_RE.finditer(txt):
            urls.add(m.group(0))
    return sorted(urls)


def local_path(url_path: str) -> Path:
    """Map /wp-content/uploads/foo to <ROOT>/wp-content/uploads/foo, decoding %-escapes."""
    decoded = urllib.parse.unquote(url_path.lstrip("/"))
    return ROOT / decoded


def fetch(url_path: str):
    dst = local_path(url_path)
    if dst.exists() and dst.stat().st_size > 0:
        return ("skip", url_path)
    # URL-encode non-ASCII path segments (file names are often Japanese)
    encoded_path = urllib.parse.quote(url_path, safe="/@-._%~")
    full = ORIGIN + encoded_path
    try:
        req = urllib.request.Request(
            full,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return ("too_big", url_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return ("ok", url_path)
    except Exception as exc:
        return (f"err:{exc.__class__.__name__}", url_path)


def main():
    urls = collect_urls()
    print(f"collected {len(urls)} unique upload URLs")
    counts = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch, u) for u in urls]
        for i, fut in enumerate(as_completed(futures), 1):
            status, u = fut.result()
            counts[status] = counts.get(status, 0) + 1
            if i % 50 == 0:
                print(f"  ... {i}/{len(urls)}", file=sys.stderr)
    for status, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {status}: {n}")


if __name__ == "__main__":
    main()
