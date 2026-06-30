from datetime import datetime, timezone

from digest.dedup import dedup_within_day
from digest.models import Item


def _item(source, id, url, title, summary):
    return Item(source=source, id=id, title=title, url=url,
                published=datetime(2026, 6, 30, tzinfo=timezone.utc), summary=summary)


def test_within_day_merges_semantic_duplicate_and_keeps_distinct():
    items = [
        _item("openai", "1", "https://openai.com/gpt5", "GPT-5 released",
              "OpenAI released GPT-5 today, its newest flagship model."),
        _item("news", "2", "https://news.site/gpt5-coverage", "OpenAI ships GPT-5",
              "OpenAI has shipped GPT-5."),
        _item("arxiv", "3", "https://arxiv.org/abs/x", "A CUDA attention kernel",
              "A faster fused attention kernel for GPUs."),
    ]
    # Fake embeddings: items 0 and 1 near-identical; 2 orthogonal.
    fake_vecs = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
    out = dedup_within_day(
        items,
        embed_fn=lambda texts: fake_vecs,
        same_story_fn=lambda items, pairs: set(pairs),  # not needed here (above HIGH)
    )
    assert len(out) == 2
    canonical = next(i for i in out if i.source in ("openai", "news"))
    assert len(canonical.summary) >= len("OpenAI has shipped GPT-5.")  # richer kept
    assert canonical.merged_sources                                    # absorbed the other


def test_within_day_falls_back_to_exact_when_embeddings_unavailable():
    items = [
        _item("openai", "1", "https://openai.com/gpt5", "GPT-5", "x"),
        _item("news", "2", "https://www.openai.com/gpt5/", "GPT-5 again", "y"),
        _item("arxiv", "3", "https://arxiv.org/abs/x", "Paper", "z"),
    ]
    out = dedup_within_day(items, embed_fn=lambda texts: None,
                           same_story_fn=lambda items, pairs: set())
    assert len(out) == 2                       # exact pass still collapsed the two urls
