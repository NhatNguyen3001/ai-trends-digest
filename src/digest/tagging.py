"""Entity/topic tagging: Claude extracts typed tags for cross-reference grouping.

One batched structured-output call tags every top-N item with typed entities
(model/org/technique/dataset/task). We normalise the names, dedup within each item,
and store them on ``Item.tags``. A pure ``build_tag_index`` then groups items that
share a tag. Annotate-only (never touches ranking/dedup); whole-batch soft-fail so a
tagging error just leaves items untagged and the digest still ships.
"""

import re
import sys

from typing import Literal

from pydantic import BaseModel

from digest import config
from digest.llm import get_client
from digest.models import Item, Tag


def _normalize(name: str) -> str:
    """Trim and collapse internal whitespace; the human-readable display form.

    Case is preserved on purpose ("RAG", "GPT-4" must stay intact). Case-insensitive
    grouping is handled by build_tag_index, not here.
    """
    return re.sub(r"\s+", " ", name).strip()


def _dedup_tags(tags: list[Tag]) -> list[Tag]:
    """Drop exact (type, case-insensitive name) repeats, preserving first-seen order."""
    seen: set[tuple[str, str]] = set()
    out: list[Tag] = []
    for t in tags:
        key = (t.type, t.name.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


TagType = Literal["model", "org", "technique", "dataset", "task"]


class TagOut(BaseModel):
    name: str
    type: TagType


class ItemTags(BaseModel):
    index: int
    tags: list[TagOut]


class Tagging(BaseModel):
    items: list[ItemTags]


SYSTEM = (
    "You tag AI news, papers, and tools for a daily digest read by an AI engineer "
    "who follows LLMs, agents, and RAG. For each item, extract the concrete named "
    "entities and topics it is actually about, each with a type:\n"
    "- model: a named model or model family (e.g. 'Llama 3', 'GPT-4', 'Claude')\n"
    "- org: a lab, company, or group (e.g. 'DeepMind', 'Meta', 'OpenAI')\n"
    "- technique: a method or approach (e.g. 'RAG', 'RLHF', 'chain-of-thought')\n"
    "- dataset: a named dataset or benchmark (e.g. 'ImageNet', 'MMLU')\n"
    "- task: a problem area (e.g. 'code generation', 'summarization')\n"
    "Use the canonical short name (prefer 'RAG' over 'retrieval-augmented "
    "generation', 'Llama 3' over 'LLaMA-3'). Only tag what the item is clearly "
    "about; omit vague or speculative tags. An item may have zero tags."
)


def _tag(items, client_factory) -> Tagging:
    numbered = "\n\n".join(
        f"[{i}] Title: {it.title}\nText: {it.summary}" for i, it in enumerate(items)
    )
    instruction = (
        f"Tag each of the {len(items)} items below. Return a tag object for every "
        f"index from 0 to {len(items) - 1} (use an empty tag list if an item has no "
        f"clear entities).\n\n{numbered}"
    )
    client = client_factory()
    response = client.messages.parse(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": instruction}],
        output_format=Tagging,
    )
    return response.parsed_output


def tag_items(items, *, client_factory=get_client) -> None:
    """Annotate each item's ``tags`` in place from one batched Claude call.

    Index-keyed (a dropped index just leaves that item untagged). Whole-batch
    soft-fail: any error logs to stderr and leaves every item's tags empty."""
    if not items:
        return

    try:
        tagging = _tag(items, client_factory)
    except Exception as exc:  # noqa: BLE001 — tagging is best-effort
        print(f"[tagging] tagging failed ({exc}); delivering items untagged.",
              file=sys.stderr)
        return

    by_index = {t.index: t for t in tagging.items}
    for i, it in enumerate(items):
        t = by_index.get(i)
        if t is None:                                  # model dropped this index
            continue
        tags = [Tag(name=_normalize(to.name), type=to.type)
                for to in t.tags if _normalize(to.name)]
        it.tags = _dedup_tags(tags)


def build_tag_index(items: list[Item]) -> dict[tuple[str, str], list[int]]:
    """Group items that share a tag. Returns {(type, display_name): [ranks...]}.

    Ranks are 1-based positions in ``items``. Grouping is case-insensitive on the
    name (so "RAG"/"rag" merge) but the display name keeps its first-seen casing.
    Only groups with >= 2 distinct members are returned; key order is sorted for
    stable output.
    """
    groups: dict[tuple[str, str], dict] = {}   # (type, casefold) -> {display, ranks}
    for rank, it in enumerate(items, start=1):
        for tag in it.tags:
            key = (tag.type, tag.name.casefold())
            g = groups.setdefault(key, {"display": tag.name, "ranks": []})
            if rank not in g["ranks"]:
                g["ranks"].append(rank)

    index = {
        (type_, g["display"]): g["ranks"]
        for (type_, _cf), g in groups.items()
        if len(g["ranks"]) >= 2
    }
    return dict(sorted(index.items()))
