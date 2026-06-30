import digest.embeddings as emb


class _FakeResult:
    def __init__(self, vectors):
        self.embeddings = vectors


class _FakeClient:
    def __init__(self, *a, **k):
        self.calls = []

    def embed(self, texts, model, input_type):
        self.calls.append(len(texts))
        return _FakeResult([[0.1, 0.2, 0.3] for _ in texts])


def test_embed_texts_returns_one_vector_per_text(monkeypatch):
    monkeypatch.setattr(emb.config, "VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(emb.voyageai, "Client", _FakeClient)
    out = emb.embed_texts(["a", "b", "c"])
    assert out is not None
    assert len(out) == 3
    assert out[0] == [0.1, 0.2, 0.3]


def test_embed_texts_batches_over_128(monkeypatch):
    seen = {}

    class _Counting(_FakeClient):
        def embed(self, texts, model, input_type):
            seen.setdefault("batches", []).append(len(texts))
            return _FakeResult([[0.0] for _ in texts])

    monkeypatch.setattr(emb.config, "VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(emb.voyageai, "Client", _Counting)
    emb.embed_texts(["x"] * 200)
    assert seen["batches"] == [128, 72]        # split into <=128 chunks


def test_embed_texts_soft_fails_to_none(monkeypatch):
    class _Boom(_FakeClient):
        def embed(self, *a, **k):
            raise RuntimeError("voyage down")

    monkeypatch.setattr(emb.config, "VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(emb.voyageai, "Client", _Boom)
    assert emb.embed_texts(["a"]) is None       # degrades, does not raise
