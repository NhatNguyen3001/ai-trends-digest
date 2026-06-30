from datetime import date, datetime, timedelta, timezone

import pytest

from digest import memory_store as ms
from digest.models import Item


def _item(url, title="t", summary="s", source="x", id="i"):
    return Item(source=source, id=id, title=title, url=url,
                published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary)


@pytest.fixture
def store():
    return ms.get_store(path=None, dim=2)  # in-memory, tiny vectors


def test_remember_then_search_finds_nearest_before_today(store):
    yesterday = date(2026, 6, 29)
    today = date(2026, 6, 30)
    ms.remember(store,
                items=[_item("https://a.com/x"), _item("https://b.com/y")],
                vectors=[[1.0, 0.0], [0.0, 1.0]],
                run_date=yesterday)
    hit = ms.search_similar(store, [1.0, 0.0], before=today)
    assert hit is not None
    assert hit.payload["url"] == "https://a.com/x"
    assert hit.score > 0.99


def test_search_excludes_points_dated_on_or_after_before(store):
    today = date(2026, 6, 30)
    ms.remember(store, items=[_item("https://a.com/x")], vectors=[[1.0, 0.0]],
                run_date=today)                       # stored as "today"
    # window is strictly before today -> today's own point must not match
    assert ms.search_similar(store, [1.0, 0.0], before=today) is None


def test_prune_deletes_only_old_points(store):
    today = date(2026, 6, 30)
    old = today - timedelta(days=20)
    recent = today - timedelta(days=3)
    ms.remember(store, items=[_item("https://old.com/x")], vectors=[[1.0, 0.0]], run_date=old)
    ms.remember(store, items=[_item("https://new.com/y")], vectors=[[0.0, 1.0]], run_date=recent)
    ms.prune(store, today=today, days=14)
    # The old point is gone: a search near its vector must not return it (the only
    # survivor is the recent point, which sits far away).
    old_hit = ms.search_similar(store, [1.0, 0.0], before=today)
    assert old_hit is None or old_hit.payload["url"] != "https://old.com/x"
    hit = ms.search_similar(store, [0.0, 1.0], before=today)
    assert hit is not None and hit.payload["url"] == "https://new.com/y"   # recent kept
