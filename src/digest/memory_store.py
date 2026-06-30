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

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from qdrant_client import QdrantClient, models

from digest import config
from digest.dedup import _normalize_url
from digest.models import Item

_COLLECTION = "seen_stories"
# Fixed namespace so the same URL always hashes to the same point id across runs.
_NAMESPACE = uuid.UUID("1b671a64-40d5-491e-99b0-da01ff1f3341")


@dataclass
class Hit:
    score: float
    payload: dict


def get_store(path: str | None = None, dim: int | None = None) -> QdrantClient:
    """Open the store (on-disk at ``path``, or in-memory when None) and ensure the
    collection exists with the right vector size + cosine distance.

    ``dim`` defaults to the production embedding size; tests pass a small value to
    keep fixtures readable.
    """
    client = QdrantClient(path=path) if path else QdrantClient(":memory:")
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


def prune(store, today: date, days: int = 14) -> None:
    """Delete points older than ``today - days``."""
    cutoff = (today - timedelta(days=days)).toordinal()
    store.delete(
        collection_name=_COLLECTION,
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="date_ord", range=models.Range(lt=cutoff))])),
    )
