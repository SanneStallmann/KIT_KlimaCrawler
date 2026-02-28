# crawler/core/parsers/html_parser.py
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from crawler.core.models import ParseResult, Segment, FetchResult


MIN_SEGMENT_LENGTH = 30

# conservative skip list for obvious non-document assets
BLOCKED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".mp4", ".mp3", ".avi", ".mov", ".mkv",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".ico",
)

# remove clearly non-content and high-noise boilerplate containers
DROP_TAGS = ("script", "style", "noscript", "svg")
DROP_SECTIONS = ("nav", "footer", "aside")


_RE_WS = re.compile(r"\s+")
_RE_MULTI_SLASH = re.compile(r"/{2,}")


def _clean_text(text: str) -> str:
    return _RE_WS.sub(" ", text or "").strip()


def _looks_like_asset(url: str) -> bool:
    u = (url or "").lower().split("?", 1)[0]
    return any(u.endswith(ext) for ext in BLOCKED_EXTENSIONS)


def _is_http_url(url: str) -> bool:
    try:
        s = urlsplit(url)
    except Exception:
        return False
    return s.scheme in ("http", "https") and bool(s.netloc)


def _dedup_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for u, a in links:
        if u in seen:
            continue
        seen.add(u)
        out.append((u, a))
    return out


def parse_html(fetch_result: FetchResult, base_url: str) -> ParseResult:
    body = fetch_result.body or b""
    if not body:
        return ParseResult(text="", segments=[], out_links=[], meta={})

    try:
        soup = BeautifulSoup(body, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(body, "html.parser")
        except Exception:
            return ParseResult(text="", segments=[], out_links=[], meta={})

    for tag in soup(DROP_TAGS):
        tag.decompose()

    for tag in soup.find_all(DROP_SECTIONS):
        tag.decompose()

    segments: list[Segment] = []
    order = 0

    min_len = int(MIN_SEGMENT_LENGTH)

    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        txt = _clean_text(tag.get_text(" ", strip=True))
        if not txt or len(txt) < min_len:
            continue

        name = tag.name or ""
        if name.startswith("h"):
            seg_type = "heading"
        elif name == "li":
            seg_type = "list_item"
        else:
            seg_type = "paragraph"

        segments.append(Segment(order_index=order, segment_type=seg_type, text=txt))
        order += 1

    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href:
            continue

        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        abs_url = urljoin(base_url, href)

        try:
            p = urlsplit(abs_url)
            if p.path and "//" in p.path:
                abs_url = abs_url.replace(p.path, _RE_MULTI_SLASH.sub("/", p.path), 1)
        except Exception:
            pass

        if not _is_http_url(abs_url):
            continue
        if _looks_like_asset(abs_url):
            continue

        anchor = _clean_text(a.get_text(" ", strip=True))
        links.append((abs_url, anchor))

    links = _dedup_links(links)

    title_tag = soup.find("title")
    title = _clean_text(title_tag.get_text()) if title_tag else None

    full_text = _clean_text(soup.get_text(" ", strip=True))

    meta = {}
    if title:
        meta["title"] = title
    if fetch_result.content_type:
        meta["content_type"] = fetch_result.content_type

    return ParseResult(
        text=full_text,
        segments=segments,
        out_links=links,
        meta=meta,
    )
