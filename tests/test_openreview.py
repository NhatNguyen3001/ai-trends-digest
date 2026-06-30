import digest.openreview as orv


def test_norm_title_ignores_case_and_punctuation():
    assert orv._norm_title("Mamba: Linear-Time!") == orv._norm_title("mamba linear time")


def test_decision_from_venue():
    assert orv._decision_from_venue("ICLR 2024 Oral") == "accepted (oral)"
    assert orv._decision_from_venue("ICLR 2024 Spotlight") == "accepted (spotlight)"
    assert orv._decision_from_venue("ICLR 2024 Poster") == "accepted (poster)"
    assert orv._decision_from_venue("Submitted to ICLR 2024") == "under review"
    assert orv._decision_from_venue("ICLR 2024 Reject") == "rejected"
    assert orv._decision_from_venue("NeurIPS 2024") == "accepted"


def _search(notes):
    return {"notes": notes}


def _note(title, venue, venueid, forum="f1"):
    return {"id": forum, "forum": forum, "content": {
        "title": {"value": title},
        "venue": {"value": venue},
        "venueid": {"value": venueid},
    }}


def test_lookup_skips_dblp_mirror(monkeypatch):
    # Only a CoRR/DBLP mirror is returned -> no reviewed record.
    monkeypatch.setattr(orv, "_get_json", lambda url: _search([
        _note("Mamba", "CoRR 2023", "dblp.org/journals/CORR/2023"),
    ]))
    assert orv.lookup_openreview("Mamba") is None


def test_lookup_returns_reviewed_note_with_rating(monkeypatch):
    def fake_get(url):
        if "search" in url:
            return _search([
                _note("Mamba", "CoRR 2023", "dblp.org/journals/CORR/2023"),
                _note("Mamba", "ICLR 2024 Poster", "ICLR.cc/2024/Conference", forum="f9"),
            ])
        # forum replies (reviews carry a rating)
        return {"notes": [
            {"content": {"rating": {"value": "8: accept"}}},
            {"content": {"rating": {"value": "6: marginal"}}},
            {"content": {"decision": {"value": "Accept (Poster)"}}},  # no rating, ignored
        ]}

    monkeypatch.setattr(orv, "_get_json", fake_get)
    res = orv.lookup_openreview("Mamba")
    assert res is not None
    assert res.venue == "ICLR 2024 Poster"
    assert res.decision == "accepted (poster)"
    assert res.avg_rating == 7.0          # (8 + 6) / 2
    assert res.num_reviews == 2


def test_lookup_empty_search_returns_none(monkeypatch):
    monkeypatch.setattr(orv, "_get_json", lambda url: _search([]))
    assert orv.lookup_openreview("nothing") is None


def test_lookup_soft_fails_on_error(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")
    monkeypatch.setattr(orv, "_get_json", boom)
    assert orv.lookup_openreview("Mamba") is None
