from datetime import datetime, timezone
from types import SimpleNamespace

from digest.ranking import rank_items, Ranking, ItemScore
from digest.models import Item


def _item(title, summary="s"):
    return Item(source="x", id=title, title=title, url="u",
                published=datetime(2026, 7, 1, tzinfo=timezone.utc), summary=summary)


def _client_returning(ranking):
    class _Msgs:
        def parse(self, **kwargs):
            return SimpleNamespace(parsed_output=ranking)
    class _Client:
        messages = _Msgs()
    return lambda: _Client()


def _boom_client():
    class _Msgs:
        def parse(self, **kwargs):
            raise RuntimeError("api down")
    class _Client:
        messages = _Msgs()
    return _Client()


def test_rank_sorts_by_blended_score_and_truncates():
    items = [_item("A"), _item("B"), _item("C")]
    ranking = Ranking(scores=[
        ItemScore(index=0, significance=2, novelty=2, relevance=2, reason="meh"),
        ItemScore(index=1, significance=10, novelty=9, relevance=10, reason="huge"),
        ItemScore(index=2, significance=6, novelty=5, relevance=6, reason="ok"),
    ])
    out = rank_items(items, top_n=2, client_factory=_client_returning(ranking))
    assert [it.title for it in out] == ["B", "C"]      # sorted desc, top 2
    assert out[0].score > out[1].score
    assert out[0].score_reason == "huge"


def test_rank_missing_index_gets_neutral_default():
    items = [_item("A"), _item("B")]
    ranking = Ranking(scores=[
        ItemScore(index=0, significance=9, novelty=9, relevance=9, reason="top"),
    ])  # index 1 missing
    out = rank_items(items, client_factory=_client_returning(ranking))
    b = next(it for it in out if it.title == "B")
    assert b.score_reason == "(unscored)"
    assert b.score == 5.0                              # blend of 5/5/5


def test_rank_clamps_out_of_range_scores():
    items = [_item("A")]
    ranking = Ranking(scores=[
        ItemScore(index=0, significance=99, novelty=-4, relevance=10, reason="wild"),
    ])
    out = rank_items(items, client_factory=_client_returning(ranking))
    # clamped: sig 10, nov 0, rel 10 -> 0.5*10 + 0.3*10 + 0.2*0 = 8.0
    assert out[0].score == 8.0


def test_rank_soft_fails_to_unchanged_items():
    items = [_item("A"), _item("B")]
    out = rank_items(items, top_n=1, client_factory=_boom_client)
    assert out == items                                # unranked, unfiltered
    assert out[0].score == 0.0


def test_rank_empty_returns_empty():
    assert rank_items([], client_factory=_boom_client) == []
