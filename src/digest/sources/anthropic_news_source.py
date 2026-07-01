"""Collect recent posts from Anthropic's company news (anthropic.com/news).

A second Anthropic source alongside ``anthropic_source`` (claude.com/blog): the
Claude *product* blog and the company *news* feed are different pages with different
posts, so we collect both. Neither has an RSS feed, so this reuses the same scrape
approach (JSON-LD ``Article`` + Open Graph) via ``scrape_blog`` — only the site and
the ``source`` label differ.
"""

from digest.models import Item
from digest.sources.anthropic_source import scrape_blog

BASE = "https://www.anthropic.com"


def fetch_anthropic_news(max_results: int = 5) -> list[Item]:
    """Return recent anthropic.com/news posts as normalised ``Item``s.

    Soft-fails to an empty list (with a warning) on any error, like every collector.
    """
    return scrape_blog(BASE, "/news", "/news/", "Anthropic News", max_results)
