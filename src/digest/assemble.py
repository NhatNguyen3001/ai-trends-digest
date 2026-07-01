"""Assemble the ranked/summarised items into the daily markdown digest.

Three units, deliberately separated by concern:
- ``render_digest`` — PURE. Builds the markdown string from items + summaries. No
  file I/O, no network, no LLM, so it is fully unit-testable and can never fail on
  those. This is the format of the daily deliverable.
- ``write_intro`` — the one LLM call (a short "today at a glance" blurb). Soft-fails
  to "" so a bad call never costs us the digest.
- ``write_digest_file`` — writes the markdown to ``digests/YYYY-MM-DD.md``.

The digest is ranked, so items render in delivery order; each shows the pipeline's
judgment (score + reason, significance, tags) for transparency. The "Related by tag"
section reuses slice F's ``build_tag_index`` rather than re-deriving grouping.
"""

import sys
from datetime import date
from pathlib import Path

from digest import config
from digest.llm import get_client
from digest.models import Item
from digest.tagging import build_tag_index


_INTRO_SYSTEM = (
    "You write the one-paragraph opener for a daily AI-trends digest read by an AI "
    "engineer who follows LLMs, agents, and RAG. Given today's top items, write 2-3 "
    "plain-English sentences on what stands out today. Be concrete, no hype, no lists, "
    "no markdown — just the paragraph."
)


def write_intro(items, *, client_factory=get_client) -> str:
    """One short 'today at a glance' blurb. Soft-fails to '' on any error."""
    if not items:
        return ""
    top = "\n".join(
        f"- {it.title}" + (f" — {it.score_reason}" if it.score_reason else "")
        for it in items
    )
    try:
        client = client_factory()
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=300,
            system=_INTRO_SYSTEM,
            messages=[{"role": "user",
                       "content": f"Today's top items:\n\n{top}\n\nWrite the opener."}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except Exception as exc:  # noqa: BLE001 — intro is best-effort
        print(f"[assemble] intro failed ({exc}); rendering without it.",
              file=sys.stderr)
        return ""


def _source_counts_line(items: list[Item]) -> str:
    """`N items · src1, src2` — sources in first-appearance order."""
    seen: list[str] = []
    for it in items:
        if it.source not in seen:
            seen.append(it.source)
    sources = ", ".join(seen)
    tail = f" · {sources}" if sources else ""
    return f"{len(items)} items{tail}"


def _item_block(rank: int, item: Item, summary: str) -> str:
    """One item's markdown section. Optional fields render only when present."""
    lines = [f"## {rank}. [{item.title}]({item.url})"]
    lines.append(f"**{item.source}** · score {item.score:.1f} · {item.score_reason}")
    if item.significance_note:
        lines.append(f"significance: {item.significance_note}")
    if item.tags:
        tags = ", ".join(f"{t.name} ({t.type})" for t in item.tags)
        lines.append(f"tags: {tags}")
    lines.append("")
    lines.append(summary)
    if item.merged_sources:
        lines.append("")
        lines.append(f"also covered by: {', '.join(item.merged_sources)}")
    return "\n".join(lines)


def render_digest(items: list[Item], summaries: list[str], run_date: date,
                  intro: str = "") -> str:
    """Build the full daily digest markdown. Pure — no I/O, no network."""
    parts = [f"# AI Trends Digest — {run_date:%Y-%m-%d}"]
    if intro:
        parts.append(f"_{intro}_")
    parts.append(_source_counts_line(items))
    if items:
        parts.append("---")
        for rank, (item, summary) in enumerate(zip(items, summaries), start=1):
            parts.append(_item_block(rank, item, summary))

    tag_index = build_tag_index(items)
    if tag_index:
        parts.append("---")
        lines = ["## Related by tag", ""]
        for (type_, name), ranks in tag_index.items():
            joined = ", ".join(f"#{r}" for r in ranks)
            lines.append(f"- {name} ({type_}): {joined}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) + "\n"


def write_digest_file(markdown: str, run_dt, out_dir=None) -> Path:
    """Write the digest to <out_dir>/YYYY-MM-DD_HH-MM-SS.md (utf-8); return the Path.

    ``run_dt`` is the run's ``datetime`` — the time is in the filename so two runs on
    the same day each get their own file instead of overwriting. (A plain ``date``
    also works; its time renders as 00-00-00.)
    """
    directory = Path(out_dir if out_dir is not None else config.DIGEST_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_dt:%Y-%m-%d_%H-%M-%S}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
