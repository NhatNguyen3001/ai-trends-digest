"""Collect 'trending-ish' AI repositories from GitHub.

GitHub has no official *trending* API — github.com/trending is just an HTML page.
Rather than scrape it, we approximate trending with the official **Search API**:
recently-created repositories in AI topics, sorted by stars. A repo that's both
new *and* highly starred is a good "trending in AI" proxy. It's our heuristic,
not GitHub's exact trending list, but it's stable and officially supported.

We query one topic at a time and merge (de-duping by repo), which avoids the
ambiguous precedence of OR-ing topics with a date filter in a single query.

A GITHUB_TOKEN (config, optional) raises the rate limit; without one we stay
within the unauthenticated search limit (~10 requests/min), plenty here.
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from digest import config
from digest.models import Item
from digest.retry import with_retries

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.github.com/search/repositories"
DEFAULT_TOPICS = ["llm", "ai-agents", "rag"]


def _warn(message: str) -> None:
    """Non-fatal warning — a failing collector degrades to [] rather than crash."""
    log.warning("%s", message)


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-trends-digest/0.1",  # GitHub requires a User-Agent
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def _search(topic: str, qualifiers: str, per_page: int) -> list[dict]:
    """Run one Search API query: repos in `topic` matching `qualifiers`, by stars.

    `qualifiers` is the extra query text after the topic, e.g. "created:>2026-06-01"
    (trending) or "pushed:>2026-06-18 stars:>5000" (established + active).
    """
    query = f"topic:{topic} {qualifiers}"
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
    )
    req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers=_headers())

    def _do():
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8")).get("items", [])

    return with_retries(_do)


def _parse_dt(value: str | None) -> datetime:
    """GitHub timestamps look like 2026-06-20T12:34:56Z."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _since(days: int) -> str:
    """A GitHub date qualifier value: `days` ago, as YYYY-MM-DD (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _collect(
    topics: list[str],
    max_results: int,
    qualifiers: str,
    *,
    source: str,
) -> list[Item]:
    """Shared core for both GitHub lenses: query each topic with `qualifiers`,
    merge/de-dupe by repo full name, keep the most-starred, and normalise into
    ``Item``s labelled `source`.

    Soft-fails: if every topic search errors (e.g. rate-limited), returns [] with
    a warning rather than raising, so one bad source can't break the digest.
    """
    # Merge results across topics, de-duplicating by repo full name.
    by_name: dict[str, dict] = {}
    for topic in topics:
        try:
            repos = _search(topic, qualifiers, per_page=max_results)
        except Exception as exc:
            _warn(f"search for topic:{topic} failed ({type(exc).__name__}: {exc})")
            continue
        for repo in repos:
            by_name[repo["full_name"]] = repo

    if not by_name:
        _warn("no repositories returned (rate limited or all searches failed)")
        return []

    # Most-starred first across the merged set.
    ranked = sorted(
        by_name.values(), key=lambda r: r.get("stargazers_count", 0), reverse=True
    )

    items: list[Item] = []
    for repo in ranked[:max_results]:
        stars = repo.get("stargazers_count", 0)
        description = repo.get("description") or "(no description)"
        items.append(
            Item(
                source=source,
                id=repo["full_name"],          # "owner/name" — stable id
                title=repo["full_name"],
                url=repo["html_url"],
                published=_parse_dt(repo.get("created_at")),
                # Fold the star count into the text: it's the key signal for a
                # repo, and there's no dedicated stars field on Item (yet).
                summary=f"★{stars:,} stars. {description}",
                authors=[repo["owner"]["login"]] if repo.get("owner") else [],
            )
        )
    return items


def fetch_github(
    topics: list[str] | None = None,
    max_results: int = 10,
    days: int = 30,
) -> list[Item]:
    """Trending lens: recently-*created*, highly-starred AI repos.

    A repo that's both new *and* highly starred is a good "trending in AI" proxy.
    """
    qualifiers = f"created:>{_since(days)}"
    return _collect(topics or DEFAULT_TOPICS, max_results, qualifiers, source="GitHub")


def fetch_github_active(
    topics: list[str] | None = None,
    max_results: int = 10,
    days: int | None = None,
    min_stars: int | None = None,
) -> list[Item]:
    """Established + active lens: big AI repos (>= `min_stars`) *pushed* recently.

    Complements ``fetch_github``: `pushed:>` admits mature projects regardless of
    age, and the star floor keeps it to established names. Labelled "GitHub Active"
    so the digest can distinguish it from trending; both bucket as repos downstream.
    """
    days = days if days is not None else config.GITHUB_ACTIVE_DAYS
    min_stars = min_stars if min_stars is not None else config.GITHUB_MIN_STARS
    qualifiers = f"pushed:>{_since(days)} stars:>{min_stars}"
    return _collect(topics or DEFAULT_TOPICS, max_results, qualifiers,
                    source="GitHub Active")
