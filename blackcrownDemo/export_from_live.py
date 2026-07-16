"""Export Black Crown live site into this folder (GitHub Pages static demo).

Requires the Django demo server running (default http://127.0.0.1:8077).

From this directory:
    python export_from_live.py

Or with overrides:
    python export_from_live.py --base http://127.0.0.1:8077 --media-root ../../nsc/amote-core/media
"""
from __future__ import annotations

import argparse
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

SITE_PREFIX = "/live/blackcrown"
LIVE_HREF_RE = re.compile(r"""(href|action)=(["'])(/live/blackcrown[^"']*)\2""")
ABS_BASE_RE = re.compile(r"""https?://127\.0\.0\.1:\d+|https?://localhost:\d+""", re.I)

# Site pages to capture (slug -> URL path under SITE_PREFIX). Empty slug = home.
SITE_PAGES = [
    ("", "/"),
    ("about", "/about/"),
    ("sell", "/sell/"),
    ("faqs", "/faqs/"),
    ("contact", "/contact/"),
    ("buy", "/buy/"),
    ("account", "/account/"),
    ("auctions", "/auctions/"),
    ("lots", "/lots/"),
    ("article-catlett", "/article-catlett/"),
    ("article-collectors", "/article-collectors/"),
    ("article-paschke", "/article-paschke/"),
]

LOT_REFS = [
    "ap5nsloz",
    "tgrx5xvn",
    "d52lnnnq",
    "quyqre2c",
    "c7iogyvu",
    "dcwbxkl3",
    "djsmb7uf",
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "blackcrown-static-export/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def depth_for(rel_path: Path) -> int:
    """How many directories deep is this HTML file under out/?"""
    parts = rel_path.parts
    # index.html at root => 0; about/index.html => 1; lot/ref/index.html => 2
    return max(0, len(parts) - 1)


def prefix_for_depth(depth: int) -> str:
    if depth <= 0:
        return ""
    return "../" * depth


def map_live_path(path: str) -> str | None:
    """Map /live/blackcrown/... path to a static relative path (no leading ./)."""
    parsed = urlparse(path)
    p = parsed.path or "/"
    frag = ("#" + parsed.fragment) if parsed.fragment else ""
    query = ("?" + parsed.query) if parsed.query else ""

    if not p.startswith(SITE_PREFIX):
        return None
    rest = p[len(SITE_PREFIX) :] or "/"
    if not rest.startswith("/"):
        rest = "/" + rest

    # Normalize trailing slash
    if rest in ("/", ""):
        return "index.html" + query + frag

    m = re.match(r"^/lot/([^/]+)/?$", rest)
    if m:
        return f"lot/{m.group(1)}/index.html" + query + frag

    m = re.match(r"^/([^/]+)/?$", rest)
    if m:
        slug = m.group(1)
        return f"{slug}/index.html" + query + frag

    # deeper paths — keep as folders if possible
    cleaned = rest.strip("/")
    if cleaned:
        return f"{cleaned}/index.html" + query + frag
    return "index.html" + query + frag


def rewrite_html(html: str, page_rel: Path, base_origin: str) -> tuple[str, set[str]]:
    """Rewrite absolute/live/media URLs to relative paths. Return (html, media_paths)."""
    depth = depth_for(page_rel)
    pref = prefix_for_depth(depth)
    media_found: set[str] = set()

    # Strip absolute local origins first
    html = ABS_BASE_RE.sub("", html)
    html = html.replace(base_origin, "")

    # Collect media paths from the *original* absolute form only, then rewrite once.
    for m in re.finditer(r"(?<![./\w])/media/[^\s\"'<>)]+", html):
        media_found.add(m.group(0).split("?")[0])

    def media_once(m: re.Match) -> str:
        path = m.group(0)
        return pref + path.lstrip("/")

    # Only rewrite root-absolute /media/... (not already-relative ../media/...)
    html = re.sub(r"(?<![./\w])/media/[^\s\"'<>)]+", media_once, html)

    def live_sub(m: re.Match) -> str:
        attr, quote, path = m.group(1), m.group(2), m.group(3)
        mapped = map_live_path(path)
        if not mapped:
            return m.group(0)
        # Prefer clean directory links when possible for GitHub Pages
        target = mapped
        if target.endswith("/index.html"):
            target = target[: -len("index.html")]  # keep trailing slash folder
        elif target == "index.html":
            target = pref + "index.html" if pref else "./"
            return f"{attr}={quote}{target}{quote}"
        return f"{attr}={quote}{pref}{target}{quote}"

    html = LIVE_HREF_RE.sub(live_sub, html)

    # Catch remaining /live/blackcrown links in JS / other attrs
    def js_live(m: re.Match) -> str:
        path = m.group(0)
        mapped = map_live_path(path)
        if not mapped:
            return path
        if mapped.endswith("/index.html"):
            mapped = mapped[: -len("index.html")]
        elif mapped == "index.html":
            return (pref + "index.html") if pref else "./"
        return pref + mapped

    html = re.sub(r"/live/blackcrown(?:/[^\"'\s]*)?", js_live, html)

    return html, media_found


def copy_media(media_paths: set[str], media_root: Path, out: Path) -> int:
    n = 0
    for path in sorted(media_paths):
        # /media/lots/foo.jpg -> lots/foo.jpg under MEDIA_ROOT
        rel = path[len("/media/") :] if path.startswith("/media/") else path.lstrip("/")
        src = media_root / rel
        dst = out / "media" / rel
        if not src.is_file():
            print(f"  MISSING media: {src}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    return n


def write_page(out: Path, rel: Path, html: str) -> None:
    dest = out / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    print(f"  wrote {rel} ({len(html):,} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8077")
    here = Path(__file__).resolve().parent
    ap.add_argument("--out", default=str(here))
    ap.add_argument(
        "--media-root",
        default=str(here.parents[1] / "nsc" / "amote-core" / "media"),
    )
    args = ap.parse_args()
    base = args.base.rstrip("/")
    out = Path(args.out).resolve()
    media_root = Path(args.media_root).resolve()

    out.mkdir(parents=True, exist_ok=True)

    # Archive the old single-file save if present
    old = out / "Black Crown.html"
    if old.is_file():
        archive = out / "_archive"
        archive.mkdir(exist_ok=True)
        dest = archive / "Black Crown.html"
        if not dest.exists():
            shutil.move(str(old), str(dest))
            print(f"archived {old.name} -> _archive/")

    all_media: set[str] = set()
    pages: list[tuple[str, str, Path]] = []

    for slug, path in SITE_PAGES:
        url = urljoin(base + "/", (SITE_PREFIX + path).lstrip("/"))
        rel = Path("index.html") if not slug else Path(slug) / "index.html"
        pages.append((slug or "home", url, rel))

    for ref in LOT_REFS:
        url = urljoin(base + "/", f"{SITE_PREFIX.lstrip('/')}/lot/{ref}/")
        rel = Path("lot") / ref / "index.html"
        pages.append((f"lot:{ref}", url, rel))

    print(f"Exporting {len(pages)} pages -> {out}")
    print(f"Base: {base}")

    for label, url, rel in pages:
        try:
            raw = fetch(url)
        except urllib.error.HTTPError as e:
            print(f"  SKIP {label}: HTTP {e.code} {url}")
            continue
        except Exception as e:
            print(f"  SKIP {label}: {e}")
            continue
        rewritten, media = rewrite_html(raw, rel, base)
        all_media |= media
        write_page(out, rel, rewritten)

    # Always include all lot images on disk (covers gallery extras)
    lots_dir = media_root / "lots"
    if lots_dir.is_dir():
        for f in lots_dir.rglob("*"):
            if f.is_file():
                all_media.add("/media/lots/" + f.relative_to(lots_dir).as_posix())

    print(f"Copying {len(all_media)} media files from {media_root}")
    n = copy_media(all_media, media_root, out)
    print(f"Copied {n} media files")

    nojekyll = out / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")

    readme = out / "README.md"
    if not readme.exists():
        readme.write_text(
            """# Black Crown — static demo

Frozen HTML snapshot for GitHub Pages. Open `index.html`, or run `python export_from_live.py` to refresh from the live server.
""",
            encoding="utf-8",
        )
    print("Done.")


if __name__ == "__main__":
    main()
