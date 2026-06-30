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


def rank_items(items, *, top_n=None, client_factory=get_client):
    """Score items, set item.score/score_reason, return the top-N sorted by score.

    Soft-fail: any error returns the items unchanged (unranked, unfiltered)."""
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

    ranked = sorted(items, key=lambda it: it.score, reverse=True)
    return ranked[:top_n] if top_n else ranked
