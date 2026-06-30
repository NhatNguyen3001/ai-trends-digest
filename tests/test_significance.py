from datetime import datetime, timezone
from types import SimpleNamespace

from digest.significance import enrich_significance
from digest.openreview import OpenReviewResult
from digest.models import Item


def _item(source, title):
    return Item(source=source, id=title, title=title, url="u",
                published=datetime(2026, 7, 1, tzinfo=timezone.utc), summary="s")


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(tool_id, name, inp):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=inp)


class _ScriptedMessages:
    """First create() asks for the tool; second returns the final sentence."""
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        c = self._client
        c.turns += 1
        if c.turns == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[_tool_block("t1", "lookup_openreview", {"title": "Mamba"})],
            )
        return SimpleNamespace(stop_reason="end_turn", content=[_text_block(c.final)])


class _ScriptedClient:
    def __init__(self, final_text="Accepted at ICLR 2024 (Poster), avg rating 7.0."):
        self.turns = 0
        self.final = final_text
        self.messages = _ScriptedMessages(self)


class _BoomMessages:
    def create(self, **kwargs):
        raise RuntimeError("api down")


class _BoomClient:
    messages = _BoomMessages()


def _result():
    return OpenReviewResult(venue="ICLR 2024 Poster", decision="accepted (poster)",
                            avg_rating=7.0, num_reviews=3)


def test_enrich_sets_note_on_arxiv_paper():
    items = [_item("arxiv", "Mamba")]
    enrich_significance(items, client_factory=lambda: _ScriptedClient(),
                        lookup_fn=lambda title: _result())
    assert items[0].significance_note == "Accepted at ICLR 2024 (Poster), avg rating 7.0."


def test_enrich_skips_non_arxiv_items():
    items = [_item("github", "some/repo")]
    called = {"n": 0}

    def _factory():
        called["n"] += 1
        return _ScriptedClient()

    enrich_significance(items, client_factory=_factory, lookup_fn=lambda title: _result())
    assert items[0].significance_note == ""
    assert called["n"] == 0                            # no client built for non-papers


def test_enrich_handles_no_record():
    items = [_item("arxiv", "Obscure preprint")]
    enrich_significance(
        items,
        client_factory=lambda: _ScriptedClient(final_text="No peer-review record found."),
        lookup_fn=lambda title: None,                  # lookup finds nothing
    )
    assert items[0].significance_note == "No peer-review record found."


def test_enrich_soft_fails_per_item():
    items = [_item("arxiv", "Mamba")]
    enrich_significance(items, client_factory=lambda: _BoomClient(),
                        lookup_fn=lambda title: _result())
    assert items[0].significance_note == ""            # left empty, no raise
