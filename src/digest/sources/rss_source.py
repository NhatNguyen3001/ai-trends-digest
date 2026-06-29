"""Fetch recent posts from a curated list of AI blogs/newsletters via RSS.

RSS is a *transport*, not a single source: one parser (``feedparser``) unlocks
many publishers at once. "Adding a source" is just adding a URL to ``FEEDS``.

Each entry is normalised into the same ``Item`` shape as every other collector.
We set ``Item.source`` to the *publisher name* (e.g. "NVIDIA") rather than a
generic "rss", because the publisher is what matters for the digest and for the
later "source credibility" ranking signal.
"""

import calendar
import re
from datetime import datetime, timezone

import feedparser

from digest.models import Item

# Publisher name -> feed URL. URLs move; the collector skips any that fail so a
# dead feed never breaks a run. Trim or extend this list freely.
FEEDS: dict[str, str] = {
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "NVIDIA": "https://developer.nvidia.com/blog/feed/",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "OpenAI": "https://openai.com/news/rss.xml",
    "BAIR": "https://bair.berkeley.edu/blog/feed.xml",
    # Anthropic: no public RSS feed found (their /rss.xml 404s) — omitted for now.
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Feeds often put HTML in the summary; strip tags and collapse whitespace."""
    return " ".join(_TAG_RE.sub(" ", text).split())


def _entry_body(entry) -> str:
    """Pull the best available body text from a feed entry.

    Feeds disagree on where the body lives: some use ``<summary>``/``<description>``
    (feedparser -> entry.summary), others only ``<content:encoded>`` (feedparser ->
    entry.content, a list). Prefer the summary; fall back to content; else empty.
    """
    if entry.get("summary"):
        return entry["summary"]
    if entry.get("content"):
        return entry["content"][0].get("value", "")
    return ""


def _published(entry) -> datetime:
    """Convert a feed entry's parsed time to a timezone-aware UTC datetime.

    feedparser exposes ``published_parsed`` as a time.struct_time already in UTC.
    Gotcha: ``time.mktime`` would treat it as *local* time — wrong. We use
    ``calendar.timegm`` which correctly interprets the struct as UTC.
    """
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)  # fallback when the feed omits a date


def fetch_rss(feeds: dict[str, str] | None = None, max_per_feed: int = 5) -> list[Item]:
    """Return recent entries across all ``feeds``, newest-first per feed.

    Each feed is parsed independently; a feed that fails to fetch or parse is
    skipped (logged via the returned list simply not containing it) rather than
    aborting the whole run.
    """
    if feeds is None:
        feeds = FEEDS

    items: list[Item] = []
    for publisher, url in feeds.items():
        parsed = feedparser.parse(url)
        for entry in parsed.entries[:max_per_feed]:
            items.append(
                Item(
                    source=publisher,
                    id=entry.get("id") or entry.get("link", ""),
                    title=_strip_html(entry.get("title", "(untitled)")),
                    url=entry.get("link", ""),
                    published=_published(entry),
                    summary=_strip_html(_entry_body(entry)),
                    authors=[entry["author"]] if entry.get("author") else [],
                )
            )
    return items
