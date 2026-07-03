"""Turn text into vectors with Voyage AI.

One 1024-dim vector per input string, batched to keep round-trips low. Soft-fail:
any error returns None, and the caller falls back to exact-only dedup. The Voyage
client reads VOYAGE_API_KEY from the environment (loaded by config).
"""

import logging

import voyageai

from digest import config
from digest.retry import with_retries

log = logging.getLogger(__name__)

_BATCH = 128  # Voyage's recommended max texts per request


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed ``texts`` as documents. Returns one vector per text, or None on error."""
    if not texts:
        return []
    if not config.VOYAGE_API_KEY:
        log.warning("VOYAGE_API_KEY not set; skipping semantic dedup.")
        return None
    try:
        client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH):
            batch = texts[i:i + _BATCH]
            result = with_retries(lambda: client.embed(
                batch, model=config.VOYAGE_MODEL, input_type="document"))
            vectors.extend(result.embeddings)
        return vectors
    except Exception as exc:  # noqa: BLE001 — soft-fail by design
        log.warning("Voyage call failed (%s); skipping semantic dedup.", exc)
        return None
