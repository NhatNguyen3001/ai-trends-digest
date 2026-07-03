"""Tavily web-search seam — the ONLY module importing tavily. Swappable later.

Keeping the `tavily` import behind this one function means:
- tests inject a fake `search_fn` and never touch the network or need a key;
- if we swap search providers later, only this file changes.
"""
import logging

from digest import config
from digest.retry import with_retries

log = logging.getLogger(__name__)


def _client():
    # Imported lazily so a missing key/dependency only bites when a search is
    # actually attempted — importing the module (and the whole app) stays cheap.
    from tavily import TavilyClient
    return TavilyClient(api_key=config.TAVILY_API_KEY)


def web_search(query: str, *, max_results: int = 5) -> list[dict]:
    """Return [{title, url, text}] for `query`; soft-fail to [] on any error.

    A blank TAVILY_API_KEY, a network hiccup, or a Tavily error all collapse to
    an empty list so the deep-dive degrades gracefully rather than crashing.
    """
    try:
        raw = with_retries(lambda: _client().search(query, max_results=max_results))
    except Exception as exc:  # noqa: BLE001 — search is best-effort
        log.warning("search failed (%s: %s)", type(exc).__name__, exc)
        return []
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "text": r.get("content", "")} for r in raw.get("results", [])]
