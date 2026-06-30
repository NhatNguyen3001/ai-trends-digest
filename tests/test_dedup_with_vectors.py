from datetime import datetime, timezone

from digest.dedup import dedup_within_day_with_vectors
from digest.models import Item


def _item(source, id, url, title, summary):
    return Item(source=source, id=id, title=title, url=url,
                published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary)


def test_with_vectors_returns_survivors_aligned_with_their_vectors():
    items = [
        _item("openai", "1", "https://openai.com/gpt5", "GPT-5 released",
              "OpenAI released GPT-5 today, its newest flagship model."),  # longer -> canonical
        _item("news", "2", "https://news.site/gpt5", "OpenAI ships GPT-5",
              "OpenAI shipped GPT-5."),
        _item("arxiv", "3", "https://arxiv.org/abs/x", "CUDA kernel",
              "A fused attention kernel."),
    ]
    vecs = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]  # 0 & 1 near-identical, 2 orthogonal
    kept, kept_vecs = dedup_within_day_with_vectors(
        items, vecs, same_story_fn=lambda items, pairs: set(pairs))
    assert len(kept) == 2
    assert len(kept_vecs) == 2
    # cluster {0,1} -> canonical is index 0 (richer summary), so its vector is kept
    assert kept_vecs[0] == [1.0, 0.0]
    assert kept_vecs[1] == [0.0, 1.0]


def test_with_vectors_passthrough_when_fewer_than_two():
    items = [_item("openai", "1", "https://openai.com/gpt5", "GPT-5", "x")]
    kept, kept_vecs = dedup_within_day_with_vectors(items, [[1.0, 0.0]])
    assert kept == items and kept_vecs == [[1.0, 0.0]]
