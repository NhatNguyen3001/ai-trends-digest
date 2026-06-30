from digest.ranking import _blend, _clamp, ItemScore, Ranking


def test_clamp_bounds_to_0_10():
    assert _clamp(-3) == 0
    assert _clamp(15) == 10
    assert _clamp(7) == 7
    assert _clamp(7.9) == 7        # truncates to int


def test_blend_weighted_sum():
    # weights 0.5 sig / 0.3 rel / 0.2 nov; all 10 -> 10.0
    assert _blend(10, 10, 10) == 10.0
    # significance dominates: 10/0/0 -> 5.0
    assert _blend(10, 0, 0) == 5.0
    # novelty only: 0,10,0 -> 2.0
    assert round(_blend(0, 10, 0), 6) == 2.0


def test_schema_round_trips():
    r = Ranking(scores=[ItemScore(index=0, significance=8, novelty=5, relevance=9, reason="big")])
    assert r.scores[0].index == 0
    assert r.scores[0].reason == "big"
