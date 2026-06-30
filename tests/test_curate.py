from datetime import date, datetime, timezone

from digest.curate import curate
from digest.memory_store import Hit
from digest.models import Item


def _item(source, url, title, summary="s"):
    return Item(source=source, id=url, title=title, url=url,
                published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary)


def _items3():
    return [
        _item("openai", "https://openai.com/a", "Story A", "aaaa"),
        _item("news", "https://news.site/b", "Story B", "bbbb"),
        _item("arxiv", "https://arxiv.org/c", "Story C", "cccc"),
    ]


def _vecs(texts):
    return [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]  # no pair >= SIM_LOW -> no within-day merges


def _no_merge(items, pairs):
    return set()


def test_curate_suppresses_high_score_hits(monkeypatch):
    import digest.curate as c
    monkeypatch.setattr(c, "search_similar",
                        lambda store, vector, before: Hit(0.95, {"url": "x"}))
    res = curate(_items3(), store=object(), embed_fn=_vecs,
                 same_story_fn=_no_merge, run_date=date(2026, 6, 30))
    assert res.items == []
    assert res.suppressed == 3


def test_curate_marks_mid_score_as_update(monkeypatch):
    import digest.curate as c
    monkeypatch.setattr(c, "search_similar",
                        lambda store, vector, before: Hit(0.88, {"url": "x"}))
    res = curate(_items3(), store=object(), embed_fn=_vecs,
                 same_story_fn=_no_merge, run_date=date(2026, 6, 30))
    assert len(res.items) == 3
    assert all(it.title.startswith("Update: ") for it in res.items)
    assert res.updated == 3


def test_curate_keeps_low_score_as_new(monkeypatch):
    import digest.curate as c
    monkeypatch.setattr(c, "search_similar",
                        lambda store, vector, before: Hit(0.50, {"url": "x"}))
    res = curate(_items3(), store=object(), embed_fn=_vecs,
                 same_story_fn=_no_merge, run_date=date(2026, 6, 30))
    assert len(res.items) == 3 and res.suppressed == 0 and res.updated == 0


def test_curate_soft_fails_when_store_raises(monkeypatch):
    import digest.curate as c

    def _boom(store, vector, before):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(c, "search_similar", _boom)
    res = curate(_items3(), store=object(), embed_fn=_vecs,
                 same_story_fn=_no_merge, run_date=date(2026, 6, 30))
    assert len(res.items) == 3       # all pass through as new


def test_curate_exact_only_when_embeddings_unavailable():
    res = curate(_items3(), store=object(), embed_fn=lambda texts: None,
                 same_story_fn=_no_merge, run_date=date(2026, 6, 30))
    assert len(res.items) == 3 and res.vectors == []
