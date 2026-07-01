"""Rank curated items with Claude structured outputs, then keep the top N.

One batched call scores every item on three 0-10 criteria (significance, novelty,
relevance) with a one-line reason, validated against a Pydantic schema. We clamp
the scores in code (structured outputs don't enforce numeric ranges), weight-blend
them into a single score, sort, and truncate to TOP_N. Ranking is best-effort: any
error returns the items unranked and unfiltered so the digest still ships.
"""

import sys

from pydantic import BaseModel

from digest import config
from digest.llm import get_client
from digest.models import Item


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
    """Bucket an item by source for the delivery caps: paper / repo / news."""
    if item.source == "arxiv":
        return "paper"
    if item.source == "GitHub":
        return "repo"
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
    "relevant work."
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
    response = client.messages.parse(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": instruction}],
        output_format=Ranking,
    )
    return response.parsed_output


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
        print(f"[ranking] scoring failed ({exc}); delivering items unranked.",
              file=sys.stderr)
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
        "paper": config.CAP_PAPER, "repo": config.CAP_REPO, "news": config.CAP_NEWS}

    ranked = sorted(items, key=lambda it: it.score, reverse=True)
    return _select(ranked, top_n=top_n, caps=caps, floor=floor)
