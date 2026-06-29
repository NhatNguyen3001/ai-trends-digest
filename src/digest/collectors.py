"""Run all collectors and merge their results into one list of Items.

Each collector has its own signature, so we wrap each as a named, zero-argument
callable with its per-source settings baked in here (the registry below). The
runner then calls each one uniformly, isolates failures (a crashing collector
yields [] + a warning, never aborting the others), and concatenates the results.

This is where the soft-fail pattern becomes universal: arXiv and RSS don't catch
their own network errors, but the runner's try/except does — so any single
source failing can't take down the digest.

The collectors are synchronous (blocking network I/O), so we run each in a worker
thread via ``asyncio.to_thread`` and fan them out concurrently with
``asyncio.gather``. ``collect_all`` stays a normal sync function (it drives the
event loop internally), so callers don't need to know any of this.
"""

import asyncio
import sys
from collections.abc import Callable

from digest.models import Item
from digest.sources.anthropic_source import fetch_anthropic
from digest.sources.arxiv_source import fetch_arxiv
from digest.sources.github_source import fetch_github
from digest.sources.rss_source import fetch_rss

# Source name -> a zero-arg callable returning list[Item]. Per-source counts are
# kept modest here; Phase 3's curator will rank/filter the merged pile down.
COLLECTORS: dict[str, Callable[[], list[Item]]] = {
    "arxiv": lambda: fetch_arxiv(max_results=8),
    "rss": lambda: fetch_rss(max_per_feed=3),
    "anthropic": lambda: fetch_anthropic(max_results=4),
    "github": lambda: fetch_github(max_results=6),
}


async def collect_all_async(
    collectors: dict[str, Callable[[], list[Item]]] | None = None,
) -> list[Item]:
    """Run every collector concurrently and return the merged list.

    Each collector is blocking, so ``asyncio.to_thread`` hands it to a worker
    thread and gives us an awaitable. ``asyncio.gather`` then waits for them all
    at once — because they're I/O-bound, the network waits overlap instead of
    stacking up. ``return_exceptions=True`` means one collector raising doesn't
    cancel the others (our universal soft-fail).
    """
    if collectors is None:
        collectors = COLLECTORS

    names = list(collectors)
    results = await asyncio.gather(
        *(asyncio.to_thread(collectors[name]) for name in names),
        return_exceptions=True,
    )

    items: list[Item] = []
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(
                f"[runner] collector '{name}' crashed "
                f"({type(result).__name__}: {result})",
                file=sys.stderr,
            )
            result = []
        print(f"[runner] {name}: {len(result)} items", file=sys.stderr)
        items.extend(result)

    return items


def collect_all(
    collectors: dict[str, Callable[[], list[Item]]] | None = None,
) -> list[Item]:
    """Sync entry point: run the concurrent collection and return the merged list.

    ``asyncio.run`` spins up an event loop, runs ``collect_all_async`` to
    completion, and tears the loop down — so callers stay plain synchronous code.
    """
    return asyncio.run(collect_all_async(collectors))
