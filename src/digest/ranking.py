"""Rank curated items with Claude structured outputs, then keep the top N.

One batched call scores every item on three 0-10 criteria (significance, novelty,
relevance) with a one-line reason, validated against a Pydantic schema. We clamp
the scores in code (structured outputs don't enforce numeric ranges), weight-blend
them into a single score, sort, and truncate to TOP_N. Ranking is best-effort: any
error returns the items unranked and unfiltered so the digest still ships.
"""

import logging

from pydantic import BaseModel

from digest import config
from digest.llm import get_client, parse_message
from digest.models import Item
from digest.observability import traceable

log = logging.getLogger(__name__)


class ItemScore(BaseModel):
    index: int
    significance: int
    novelty: int
    relevance: int
    reason: str


class Ranking(BaseModel):
    scores: list[ItemScore]


def _clamp(v) -> int:
    """Coerce to int and clamp to 0..10 (scores aren't schema-enforced)."""
    return max(0, min(10, int(v)))


def _blend(significance: int, novelty: int, relevance: int) -> float:
    """Weighted sum of the three criteria — the sort key."""
    return (config.W_SIGNIFICANCE * significance
            + config.W_RELEVANCE * relevance
            + config.W_NOVELTY * novelty)


def _category(item: Item) -> str:
    """Bucket an item by source for the delivery caps.

    Repos split by lens — trending (`GitHub`) vs established+active (`GitHub
    Active`) — so each is guaranteed its own share of the repo budget (5/3).
    """
    if item.source == "arxiv":
        return "paper"
    if item.source == "GitHub":
        return "repo_trending"
    if item.source == "GitHub Active":
        return "repo_active"
    return "news"                       # RSS feeds + both Anthropic scrapers (BAIR too)


def _select(items, *, top_n, caps, floor):
    """Pick the delivered items from a score-sorted list (highest first).

    Walk the list keeping each item unless it falls below ``floor`` or its
    category is already at its cap; stop at ``top_n``. Because the caps bind
    before the total does, papers can't crowd out repos/news — the next-best
    item of an un-full category takes the slot instead. A category with fewer
    than its cap simply yields fewer items (no filler)."""
    counts: dict[str, int] = {}
    out: list[Item] = []
    for it in items:
        if it.score < floor:
            continue
        cat = _category(it)
        if counts.get(cat, 0) >= caps.get(cat, top_n):
            continue
        out.append(it)
        counts[cat] = counts.get(cat, 0) + 1
        if len(out) >= top_n:
            break
    return out


SYSTEM = (
    "You rank AI news, papers, and tools for a daily digest read by an AI engineer "
    "who follows LLMs, agents, and RAG. Score how much each item deserves their "
    "attention today. Be skeptical of hype; reward genuinely significant, novel, and "
    "relevant work. In every reason you write, do not use em dashes; use commas, colons, "
    "or separate sentences instead."
)


def _score(items, client_factory) -> Ranking:
    numbered = "\n\n".join(
        f"[{i}] Title: {it.title}\nText: {it.summary}" for i, it in enumerate(items)
    )
    instruction = (
        f"Score each of the {len(items)} items below. For each, give integer scores "
        f"0-10 for significance (how big a deal), novelty (genuinely new vs "
        f"incremental), and relevance (to an AI engineer following LLMs/agents/RAG), "
        f"plus a one-sentence reason. Return a score object for every index from 0 to "
        f"{len(items) - 1}.\n\n{numbered}"
    )
    client = client_factory()
    # One score object per item (~120 tokens: 3 ints + a one-sentence reason) must
    # fit under max_tokens, or the structured-output JSON truncates mid-string and
    # parsing fails. The curated pool feeding the ranker grew with the Phase 6
    # over-collect (ARXIV_MAX/GITHUB_MAX=25), so a fixed 4000 was too small. Scale
    # with the pool, capped at a non-streaming-safe ceiling.
    max_tokens = min(16000, 2000 + 120 * len(items))
    return parse_message(
        client,
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM,
        messages=[{"role": "user", "content": instruction}],
        output_format=Ranking,
    )


@traceable
def rank_items(items, *, top_n=None, caps=None, floor=None, client_factory=get_client):
    """Score items, set item.score/score_reason, return the delivered selection.

    After scoring, delivery is balanced: sort by blended score, drop anything
    below ``floor``, and cap each source-type (paper/repo/news) so no bucket
    dominates — up to a ``top_n`` ceiling (see ``_select``). Defaults come from
    config. Soft-fail: any scoring error returns the items unchanged (unranked,
    unfiltered) so the digest still ships."""
    if not items:
        return []

    try:
        ranking = _score(items, client_factory)
    except Exception as exc:  # noqa: BLE001 — ranking is best-effort
        log.warning("scoring failed (%s); delivering items unranked.", exc)
        return items

    by_index = {s.index: s for s in ranking.scores}
    for i, it in enumerate(items):
        s = by_index.get(i)
        if s is None:                                  # model dropped this index
            it.score = _blend(5, 5, 5)
            it.score_reason = "(unscored)"
        else:
            it.score = _blend(_clamp(s.significance), _clamp(s.novelty),
                              _clamp(s.relevance))
            it.score_reason = s.reason

    top_n = top_n if top_n is not None else config.TOP_N
    floor = floor if floor is not None else config.SCORE_FLOOR
    caps = caps if caps is not None else {
        "paper": config.CAP_PAPER,
        "repo_trending": config.CAP_REPO_TRENDING,
        "repo_active": config.CAP_REPO_ACTIVE,
        "news": config.CAP_NEWS}

    ranked = sorted(items, key=lambda it: it.score, reverse=True)
    return _select(ranked, top_n=top_n, caps=caps, floor=floor)
