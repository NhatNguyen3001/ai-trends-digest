"""Summarise a batch of Items in a single Claude call.

Send all the items at once and ask Claude for a short summary of each. One call
keeps cost and latency low.

ALIGNMENT — the thing that bit us:
summaries[i] must describe items[i]. Our first version asked for a JSON *array*
and matched by position. That broke at scale: when the model dropped or merged
one item, the array came back short and every summary after the gap shifted onto
the wrong item. A length-check can detect the wrong count but can't un-shift it.

The fix: ask for a JSON *object keyed by each item's index* and look each item up
by its own key. Now a dropped item only blanks that one item — nothing else
shifts. (Phase 3 will move this to the SDK's enforced structured outputs.)
"""

import json

from digest import config
from digest.llm import get_client
from digest.models import Item
from digest.observability import traceable

SYSTEM = (
    "You summarise AI news, papers, and tools for a daily digest read by an AI "
    "engineer who follows LLMs, agents, and RAG. For each item, write one or two "
    "plain-English sentences saying what it is and why it matters. Be concrete; "
    "avoid hype and unnecessary jargon. "
    "Do not use em dashes anywhere in your output; use commas, colons, or separate "
    "sentences instead."
)


@traceable
def summarise_items(items: list[Item]) -> list[str]:
    """Return a list of short summaries, one per item, aligned with ``items``."""
    if not items:
        return []

    # Number each item so the model can key its output to the right index.
    numbered = "\n\n".join(
        f"[{i}] Title: {it.title}\nText: {it.summary}" for i, it in enumerate(items)
    )

    instruction = (
        f"Summarise each of the {len(items)} items below in one or two sentences.\n"
        f"Return ONLY a JSON object mapping each item's index (as a string key) to "
        f'its summary — e.g. {{"0": "...", "1": "..."}}. Include every index from 0 '
        f"to {len(items) - 1}. No prose, no markdown fences.\n\n"
        f"{numbered}"
    )

    client = get_client()
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4000,  # headroom for larger multi-source batches
        system=SYSTEM,
        messages=[{"role": "user", "content": instruction}],
    )

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    by_index = _parse_summaries(text)

    # Look each item up by its own index. A missing index blanks only that item.
    return [by_index.get(i, "(summary unavailable)") for i in range(len(items))]


def _parse_summaries(text: str) -> dict[int, str]:
    """Parse the model's reply into {index: summary}.

    Accepts the expected JSON object (``{"0": "..."}``); also tolerates a bare
    JSON array (mapped by position) and accidental ```json fences.
    """
    text = _strip_fences(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}

    if isinstance(data, dict):
        out: dict[int, str] = {}
        for key, value in data.items():
            try:
                out[int(key)] = str(value)
            except (ValueError, TypeError):
                continue
        return out

    if isinstance(data, list):  # fallback: positional
        return {i: str(value) for i, value in enumerate(data)}

    return {}


def _strip_fences(text: str) -> str:
    """Remove an accidental ```json ... ``` wrapper if present."""
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return text
