"""Fetch recent papers from arXiv and normalise them into ``Item``s.

This is our first *collector*. It talks to one external source (the arXiv API,
via the ``arxiv`` library) and returns a list of the pipeline's common ``Item``
type. Phase 2 will add more collectors that all return the same shape.

Note the file name: ``arxiv_source.py``, not ``arxiv.py``. If we named it
``arxiv.py``, ``import arxiv`` below could get confusing (a module shadowing the
installed library), so we keep the names distinct.
"""

import arxiv

from digest.models import Item

# arXiv subject categories we care about: Computation & Language (LLMs/NLP),
# Artificial Intelligence, and Machine Learning.
DEFAULT_CATEGORIES = ["cs.CL", "cs.AI", "cs.LG"]


def _clean(text: str) -> str:
    """Collapse whitespace — arXiv titles/abstracts contain hard line breaks."""
    return " ".join(text.split())


def fetch_arxiv(
    categories: list[str] | None = None,
    max_results: int = 10,
) -> list[Item]:
    """Return the ``max_results`` most recent arXiv papers in ``categories``.

    We don't default the argument to the list directly (``categories=DEFAULT_...``)
    because mutable default arguments are a Python footgun; we default to None
    and assign inside instead.
    """
    if categories is None:
        categories = DEFAULT_CATEGORIES

    # Build a query like: cat:cs.CL OR cat:cs.AI OR cat:cs.LG
    query = " OR ".join(f"cat:{c}" for c in categories)

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    # The Client handles paging, polite rate-limiting, and retries for us.
    client = arxiv.Client()

    items: list[Item] = []
    for result in client.results(search):
        items.append(
            Item(
                source="arxiv",
                id=result.get_short_id(),        # e.g. "2401.12345v1"
                title=_clean(result.title),
                url=result.entry_id,             # the arXiv abstract page URL
                published=result.published,      # timezone-aware datetime (UTC)
                summary=_clean(result.summary),  # the abstract
                authors=[author.name for author in result.authors],
            )
        )
    return items
