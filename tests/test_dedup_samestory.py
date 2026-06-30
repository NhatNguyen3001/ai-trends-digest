from datetime import datetime, timezone

from digest.dedup import check_same_story
from digest.models import Item


def _item(title, summary="s"):
    return Item(source="x", id="i", title=title, url="u",
                published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary)


class _Block:
    type = "text"
    def __init__(self, text): self.text = text


class _Resp:
    def __init__(self, text): self.content = [_Block(text)]


def _client_returning(text):
    class _Msgs:
        def create(self, **k): return _Resp(text)
    class _Client:
        messages = _Msgs()
    return lambda: _Client()


def test_same_story_keeps_pairs_marked_yes():
    items = [_item("GPT-5 out"), _item("OpenAI ships GPT-5"), _item("New CUDA kernel")]
    pairs = [(0, 1), (0, 2)]
    result = check_same_story(items, pairs,
                              client_factory=_client_returning('{"0": "yes", "1": "no"}'))
    assert result == {(0, 1)}


def test_same_story_soft_fails_to_empty_set():
    def _boom():
        raise RuntimeError("api down")
    items = [_item("a"), _item("b")]
    assert check_same_story(items, [(0, 1)], client_factory=_boom) == set()
