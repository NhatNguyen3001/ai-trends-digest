from datetime import datetime, timezone

from digest.dedup import _normalize_url, _exact_dedup
from digest.models import Item


def _item(source, id, url, title="t", summary="s"):
    return Item(
        source=source, id=id, title=title, url=url,
        published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary,
    )


def test_normalize_url_strips_scheme_www_slash_and_query():
    a = _normalize_url("https://www.OpenAI.com/blog/gpt-5/?utm=x")
    b = _normalize_url("http://openai.com/blog/gpt-5")
    assert a == b == "openai.com/blog/gpt-5"


def test_exact_dedup_merges_same_url_across_sources():
    items = [
        _item("openai", "1", "https://openai.com/blog/gpt-5"),
        _item("newsfeed", "2", "http://www.openai.com/blog/gpt-5/"),
        _item("arxiv", "3", "https://arxiv.org/abs/2406.0001"),
    ]
    out = _exact_dedup(items)
    assert len(out) == 2                       # the two openai links collapsed
    assert out[0].source == "openai"           # first occurrence kept
    assert out[0].merged_sources == ["newsfeed: http://www.openai.com/blog/gpt-5/"]
    assert out[1].source == "arxiv"            # untouched
