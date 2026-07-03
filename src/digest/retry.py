"""A tiny, dependency-free retry helper for the outbound network seams.

Sits INSIDE each caller's existing soft-fail, so exhausting retries still
degrades gracefully. stdlib only (no tenacity); ``time.sleep`` is monkeypatched
to a no-op in tests.
"""
import logging
import random
import time

from digest import config

log = logging.getLogger(__name__)


def with_retries(fn, *, attempts=None, base_delay=None, exceptions=(Exception,)):
    """Call ``fn()``; on a listed exception, back off and retry up to ``attempts``
    total, then re-raise the last exception."""
    attempts = attempts if attempts is not None else config.RETRY_ATTEMPTS
    base_delay = base_delay if base_delay is not None else config.RETRY_BASE_DELAY
    last = None
    for n in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if n >= attempts:
                break
            delay = base_delay * (2 ** (n - 1)) + random.uniform(0, base_delay)
            log.warning("attempt %d/%d failed (%s); retrying in %.1fs",
                        n, attempts, exc, delay)
            time.sleep(delay)
    raise last
