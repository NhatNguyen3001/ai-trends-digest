"""Curation: compose within-day dedup (slice A→B) with cross-day memory (slice C).

curate() embeds each day's items once, runs within-day dedup, then checks each
survivor against the rolling Qdrant window:
  score >= CROSS_SUPPRESS -> drop (already covered, old news)
  score >= CROSS_UPDATE   -> keep, prefix title "Update: "
  otherwise               -> keep as new
The kept items' vectors ride along so run_digest can write them back after
delivery (remember_kept) without re-embedding. Memory is best-effort: if
embeddings or the store fail, every item passes through as new.
"""

import logging
from dataclasses import dataclass, field
from datetime import date

from digest import config
from digest.dedup import _exact_dedup, check_same_story, dedup_within_day_with_vectors
from digest.embeddings import embed_texts
from digest.memory_store import prune, remember, sample_recent, search_similar
from digest.models import Item

log = logging.getLogger(__name__)


@dataclass
class CurateResult:
    items: list[Item]
    vectors: list[list[float]] = field(default_factory=list)
    suppressed: int = 0
    updated: int = 0


def curate(items, *, store=None, embed_fn=embed_texts,
           same_story_fn=check_same_story, run_date=None) -> CurateResult:
    run_date = run_date or date.today()

    items = _exact_dedup(items)
    if len(items) < 2:
        return CurateResult(items)

    texts = [f"{it.title} {it.summary}".strip() for it in items]
    vectors = embed_fn(texts)
    if vectors is None:                        # no embeddings -> exact-only, no memory
        return CurateResult(items)

    items, vectors = dedup_within_day_with_vectors(
        items, vectors, same_story_fn=same_story_fn)

    if store is None:                          # no memory configured -> all new
        return CurateResult(items, vectors)

    try:
        return _cross_day(items, vectors, store, run_date)
    except Exception as exc:  # noqa: BLE001 — memory is best-effort
        log.warning("cross-day memory unavailable (%s); keeping all as new.", exc)
        return CurateResult(items, vectors)


def _cross_day(items, vectors, store, run_date) -> CurateResult:
    kept_items: list[Item] = []
    kept_vecs: list[list[float]] = []
    suppressed = updated = 0
    for it, vec in zip(items, vectors):
        hit = search_similar(store, vec, before=run_date)
        if hit and hit.score >= config.CROSS_SUPPRESS:
            suppressed += 1
            continue
        if hit and hit.score >= config.CROSS_UPDATE:
            it.title = f"Update: {it.title}"
            updated += 1
        kept_items.append(it)
        kept_vecs.append(vec)
    return CurateResult(kept_items, kept_vecs, suppressed, updated)


def remember_kept(items, vectors, *, store, run_date: date) -> None:
    """Write the *delivered* items back to memory and prune old entries.

    Delivered-only (Phase 6): cross-day memory means "already shown to the reader,"
    not "already fetched," so the undelivered bench stays fresh for tomorrow.
    Best-effort — a store failure never blocks the digest.
    """
    if store is None or not vectors:
        return
    try:
        remember(store, items, vectors, run_date)
        prune(store, run_date, config.MEMORY_DAYS)
    except Exception as exc:  # noqa: BLE001
        log.warning("write-back failed (%s).", exc)


def select_vectors(result: CurateResult, items) -> list[list[float]]:
    """The vectors for ``items``, matched to ``result`` by object identity.

    ``rank_items`` returns the same ``Item`` objects it was given, so identity is
    preserved from ``curate`` through ranking — this recovers each delivered item's
    embedding without re-embedding. Returns ``[]`` when ``result`` carries no vectors
    (e.g. exact-only curation), which ``remember_kept`` treats as a no-op.
    """
    by_id = {id(it): v for it, v in zip(result.items, result.vectors)}
    return [by_id[id(it)] for it in items if id(it) in by_id]


def maybe_recaps(store, delivered_count: int, run_date: date, *,
                 sample_fn=sample_recent) -> list[dict]:
    """Recap payloads for a quiet day, else []. Best-effort.

    A "quiet day" is fewer than ``config.QUIET_DAY_MIN`` fresh items delivered.
    """
    if store is None or delivered_count >= config.QUIET_DAY_MIN:
        return []
    try:
        return sample_fn(store, run_date, config.QUIET_DAY_RECAPS)
    except Exception as exc:  # noqa: BLE001 — recaps are best-effort
        log.warning("recap sampling failed (%s).", exc)
        return []
