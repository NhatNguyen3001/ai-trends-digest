"""Collect recent posts from an Anthropic blog that has no RSS feed.

Anthropic publishes no RSS feed, so unlike ``rss_source`` this *scrapes*: it reads
a listing page for post links, then reads each post's own metadata for the title,
date, and summary. The core is ``scrape_blog`` — a generic scraper parameterised by
site — so more than one Anthropic property can reuse it:
  * ``fetch_anthropic``      -> claude.com/blog   (the Claude product blog)
  * ``fetch_anthropic_news`` -> anthropic.com/news (lives in ``anthropic_news_source``)

Trade-off vs RSS: scraping is more fragile. We deliberately key off two stable,
SEO-driven conventions rather than brittle CSS/div structure:
  * JSON-LD ``Article`` nodes (``headline``, ``datePublished``)
  * Open Graph meta tags (``og:description``)
If a site redesigns and drops those, this collector breaks and we fix it here —
that risk is the price of a source with no feed or API. Pure standard library.
"""

import html
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone

from digest.models import Item

log = logging.getLogger(__name__)

BASE = "https://claude.com"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; ai-trends-digest/0.1)"}


def _get(url: str) -> str:
    """Fetch a URL as text. We send a browser-ish User-Agent because some sites
    reject the default urllib agent."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def _paths_in_order(page_html: str, prefix: str) -> list[str]:
    """Return ``<prefix><slug>`` paths in document order (listing is newest-first),
    de-duplicated (a card and its title often both link to the same post)."""
    seen: list[str] = []
    for path in re.findall(rf'href="({re.escape(prefix)}[^"#?]+)"', page_html):
        if path not in seen:
            seen.append(path)
    return seen


def _meta(page_html: str, prop: str, attr: str = "property") -> str | None:
    """Read a <meta {attr}="prop" content="..."> value, tolerating either
    attribute order."""
    m = re.search(rf'<meta[^>]*{attr}="{re.escape(prop)}"[^>]*content="([^"]*)"', page_html)
    if not m:
        m = re.search(rf'<meta[^>]*content="([^"]*)"[^>]*{attr}="{re.escape(prop)}"', page_html)
    return m.group(1) if m else None


def _article_jsonld(page_html: str) -> dict:
    """Return the first JSON-LD Article node on the page, or {} if none."""
    pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    for block in re.findall(pattern, page_html, re.DOTALL):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") in (
                "BlogPosting",
                "Article",
                "NewsArticle",
            ):
                return node
    return {}


def _parse_date(value: str | None) -> datetime:
    """Parse the date formats Anthropic sites use; fall back to 'now' (UTC)."""
    if value:
        for fmt in ("%b %d, %Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def _warn(source: str, message: str) -> None:
    """Log a non-fatal warning. A failing collector should degrade to an empty
    list so the rest of the digest (arXiv, RSS) still runs — never crash the run."""
    log.warning("[%s] %s", source, message)


def scrape_blog(base: str, listing_path: str, path_prefix: str, source: str,
                max_results: int = 5) -> list[Item]:
    """Scrape a JSON-LD/Open-Graph blog into normalised ``Item``s.

    ``base`` + ``listing_path`` is the index page; ``path_prefix`` (e.g. "/blog/")
    is how we recognise a post link on it; ``source`` is the label the items carry.
    On any failure this returns an empty list with a warning rather than raising, so
    one broken source can't take down the whole digest.
    """
    # Guard 1: the listing fetch itself fails (offline, 404, timeout).
    try:
        listing = _get(base + listing_path)
    except Exception as exc:
        _warn(source, f"could not fetch listing ({type(exc).__name__}: {exc})")
        return []

    # Fetch a couple extra in case the listing order isn't strictly chronological,
    # then sort by real date below.
    slugs = _paths_in_order(listing, path_prefix)[: max_results + 2]

    # Guard 2: no post links found — the page structure probably changed.
    if not slugs:
        _warn(source, f"no {path_prefix} post links found on the listing "
                      f"(page structure changed?)")
        return []

    items: list[Item] = []
    failed = 0
    for path in slugs:
        url = base + path
        try:
            page = _get(url)
        except Exception:
            failed += 1
            continue  # skip a post that fails to load rather than abort the run

        article = _article_jsonld(page)
        # Prefer the clean JSON-LD headline; fall back to og:title (which carries a
        # " | ..." site-name suffix we trim off).
        title = article.get("headline") or (_meta(page, "og:title") or "").split(" | ")[0]
        summary = (
            _meta(page, "og:description")
            or _meta(page, "description", "name")
            or ""
        )
        published = _parse_date(
            article.get("datePublished") or _meta(page, "article:published_time")
        )

        items.append(
            Item(
                source=source,
                id=path.rsplit("/", 1)[-1],  # the slug
                # OG/meta values carry HTML entities (e.g. &#x27;); decode them.
                title=html.unescape(title).strip(),
                url=url,
                published=published,
                summary=html.unescape(summary).strip(),
                authors=[],
            )
        )

    # Guard 3: found links but couldn't parse any post (metadata format changed).
    if not items:
        _warn(source, f"found {len(slugs)} post links but parsed 0 posts "
                      f"({failed} fetch failures) — metadata format may have changed")
        return []

    items.sort(key=lambda it: it.published, reverse=True)
    return items[:max_results]


def fetch_anthropic(max_results: int = 5) -> list[Item]:
    """Return the most recent claude.com/blog posts as normalised ``Item``s."""
    return scrape_blog(BASE, "/blog", "/blog/", "Anthropic", max_results)
