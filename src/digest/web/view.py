"""Pure transform: the loaded digest dict -> a view model the template renders.

All join/format/derive logic lives here so the Jinja template stays dumb and this
stays unit-testable with no disk or network.
"""
from dataclasses import dataclass


@dataclass
class ItemView:
    index: int
    title: str
    url: str
    source_label: str
    source_bucket: str          # "arxiv" | "news" | "repo"
    date_str: str
    score: float
    score_pct: int              # 0..100 (kept for reference)
    score_pips: int             # 0..10 lit segments, score rounded to nearest
    reason: str
    summary: str
    tags: list                  # list[{"name","type"}]
    significance: str | None


@dataclass
class DigestView:
    date_str: str
    run_at: str
    stats: dict                 # {"raw","curated","delivered","floor"} (values may be None)
    source_counts: list         # list[(bucket, count)]
    intro: str
    items: list                 # list[ItemView]
    related: list               # list[(tag_name, [indices])]


def _bucket(source: str) -> str:
    s = (source or "").lower()
    if s == "arxiv":
        return "arxiv"
    if "github" in s:
        return "repo"
    return "news"


def _date_only(published) -> str:
    # published is a datetime after load_digest_data (fromisoformat); tolerate str too.
    if hasattr(published, "date"):          # datetime -> date
        return published.date().isoformat()
    return (str(published or "")).split("T", 1)[0]


def build_view(data: dict) -> DigestView:
    items = data["items"]
    summaries = data["summaries"]
    raw_stats = data.get("stats") or {}

    item_views = []
    for i, (it, summary) in enumerate(zip(items, summaries), start=1):
        item_views.append(ItemView(
            index=i,
            title=it.title,
            url=it.url,
            source_label=it.source,
            source_bucket=_bucket(it.source),
            date_str=_date_only(it.published),
            score=it.score,
            score_pct=round((it.score or 0) / 10 * 100),
            score_pips=max(0, min(10, int((it.score or 0) + 0.5))),  # round half up, 0..10
            reason=it.score_reason or "",
            summary=summary,
            tags=[{"name": t.name, "type": t.type} for t in (it.tags or [])],
            significance=it.significance_note or None,
        ))

    # source counts by bucket, stable order
    counts: dict[str, int] = {}
    for iv in item_views:
        counts[iv.source_bucket] = counts.get(iv.source_bucket, 0) + 1
    source_counts = [(b, counts[b]) for b in ("arxiv", "news", "repo") if b in counts]

    # related-by-tag: tag name -> item indices, keep only tags with >=2 members
    by_tag: dict[str, list[int]] = {}
    for iv in item_views:
        for t in iv.tags:
            by_tag.setdefault(t["name"], []).append(iv.index)
    related = sorted(((name, idxs) for name, idxs in by_tag.items() if len(idxs) >= 2),
                     key=lambda kv: (-len(kv[1]), kv[0]))

    stats = {
        "raw": raw_stats.get("raw"),
        "curated": raw_stats.get("curated"),
        "delivered": raw_stats.get("delivered", len(items)),
        "floor": raw_stats.get("floor"),
    }
    return DigestView(
        date_str=_date_only(data.get("run_at", "")),
        run_at=data.get("run_at", ""),
        stats=stats,
        source_counts=source_counts,
        intro=data.get("intro", ""),
        items=item_views,
        related=related,
    )
