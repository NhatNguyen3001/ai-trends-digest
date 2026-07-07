"""Cross-day memory: a thin wrapper around an embedded Qdrant store.

This is the ONLY module that imports qdrant_client. Everything else talks to
memory through these four functions, so swapping embedded-local for a real
Qdrant server later is a one-line change in get_store().

Each stored point is one story we've already shown: id = UUID5 of the normalized
URL (so the same link re-upserts instead of duplicating), vector = its Voyage
embedding, payload = {title, url, source, date, date_ord}. ``date_ord`` is the
day's proleptic-Gregorian ordinal (an int), which makes the 14-day window and
pruning simple numeric range filters.
"""

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from qdrant_client import QdrantClient, models

from digest import config
from digest.dedup import _normalize_url
from digest.models import Item

log = logging.getLogger(__name__)

_COLLECTION = "seen_stories"
# Fixed namespace so the same URL always hashes to the same point id across runs.
_NAMESPACE = uuid.UUID("1b671a64-40d5-491e-99b0-da01ff1f3341")


@dataclass
class Hit:
    score: float
    payload: dict


def get_store(path: str | None = None, dim: int | None = None,
              url: str | None = None) -> QdrantClient:
    """Open the store and ensure the collection exists (right vector size + cosine).

    Precedence: an explicit/config ``url`` (Qdrant server) > ``path`` (embedded on-disk) >
    ``:memory:``. ``url`` defaults to ``config.QDRANT_URL`` so a container's env selects the
    service while local runs (empty URL) keep the embedded behaviour.

    ``dim`` defaults to the production embedding size; tests pass a small value to
    keep fixtures readable.
    """
    if url is None:
        url = config.QDRANT_URL
    if url:
        client = QdrantClient(url=url)
    elif path:
        client = QdrantClient(path=path)
    else:
        client = QdrantClient(":memory:")
    names = {c.name for c in client.get_collections().collections}
    if _COLLECTION not in names:
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=models.VectorParams(
                size=dim or config.EMBED_DIM, distance=models.Distance.COSINE),
        )
    return client


def _point_id(item: Item) -> str:
    """Stable point id: UUID5 of the normalized URL (same link -> same id)."""
    return str(uuid.uuid5(_NAMESPACE, _normalize_url(item.url)))


def search_similar(store, vector, before: date):
    """Nearest stored point whose date is strictly before ``before``; or None."""
    hits = store.query_points(
        collection_name=_COLLECTION,
        query=vector,
        limit=1,
        with_payload=True,
        query_filter=models.Filter(must=[models.FieldCondition(
            key="date_ord", range=models.Range(lt=before.toordinal()))]),
    ).points
    if not hits:
        return None
    return Hit(score=hits[0].score, payload=hits[0].payload)


def remember(store, items, vectors, run_date: date) -> None:
    """Upsert one point per item, dated ``run_date``."""
    ord_ = run_date.toordinal()
    points = [
        models.PointStruct(
            id=_point_id(it),
            vector=vec,
            payload={"title": it.title, "url": it.url, "source": it.source,
                     "date": run_date.isoformat(), "date_ord": ord_},
        )
        for it, vec in zip(items, vectors)
    ]
    if points:
        store.upsert(collection_name=_COLLECTION, points=points)


def sample_recent(store, before: date, k: int, *, days: int | None = None) -> list[dict]:
    """Up to ``k`` random payloads for stored stories in the rolling window
    ``[before - days, before)``. Payload-only (no vectors). ``[]`` on any error.

    Used for quiet-day recaps. Callers write today's items back *after* delivery,
    so ``before=today`` naturally excludes today — recaps are past-only.
    """
    days = days if days is not None else config.MEMORY_DAYS
    lo = (before - timedelta(days=days)).toordinal()
    hi = before.toordinal()
    try:
        points, _ = store.scroll(
            collection_name=_COLLECTION,
            scroll_filter=models.Filter(must=[models.FieldCondition(
                key="date_ord", range=models.Range(gte=lo, lt=hi))]),
            with_payload=True, with_vectors=False, limit=10_000,
        )
    except Exception as exc:  # noqa: BLE001 — recaps are best-effort
        log.warning("sample_recent failed (%s).", exc)
        return []
    payloads = [p.payload for p in points]
    return payloads if len(payloads) <= k else random.sample(payloads, k)


def prune(store, today: date, days: int = 14) -> None:
    """Delete points older than ``today - days``."""
    cutoff = (today - timedelta(days=days)).toordinal()
    store.delete(
        collection_name=_COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="date_ord", range=models.Range(lt=cutoff))])),
    )
