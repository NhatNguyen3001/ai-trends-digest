"""Central configuration.

Every secret and tunable setting is read here, once, from the environment.
The rest of the code imports from this module instead of touching ``os.environ``
or hardcoding values. When we add Qdrant URLs, source lists, etc., they live here too.

The golden rule: real secrets live in ``.env`` (git-ignored) and never in code.
``load_dotenv()`` reads that file into the process environment at import time.
"""

import os

from dotenv import load_dotenv

# Read .env (if present) into os.environ. On a machine without a .env file
# this is a no-op — real environment variables still work (useful in CI/prod).
load_dotenv()

# --- Anthropic (Claude) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# The model the app talks to. Default matches .env.example; override in .env.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# --- GitHub (optional) ---
# A token is OPTIONAL — it only raises the Search API rate limit. The GitHub
# collector works fine without one (keyless limit is ~10 searches/min). If you
# add one, a fine-grained token needs no scopes for public repository search.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# --- Voyage AI (embeddings) ---
# Claude has no embeddings endpoint; Voyage is Anthropic's recommended partner.
# Free tier covers the first 200M tokens. Get a key at https://www.voyageai.com/.
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3.5")  # 1024-dim default
EMBED_DIM = 1024

# --- Dedup similarity thresholds (cosine) ---
# >= HIGH: clearly the same story (auto-merge). [LOW, HIGH): ask the LLM.
# < LOW: distinct. Empirical starting points; tune against real merges.
SIM_HIGH = float(os.environ.get("SIM_HIGH", "0.92"))
SIM_LOW = float(os.environ.get("SIM_LOW", "0.82"))

# --- Cross-day memory (Qdrant) ---
QDRANT_PATH = os.environ.get("QDRANT_PATH", "./data/qdrant")  # embedded on-disk store
MEMORY_DAYS = int(os.environ.get("MEMORY_DAYS", "14"))        # rolling window length
CROSS_SUPPRESS = float(os.environ.get("CROSS_SUPPRESS", "0.93"))  # >= -> drop (old news)
CROSS_UPDATE = float(os.environ.get("CROSS_UPDATE", "0.85"))      # >= -> mark "Update:"

# --- Ranking (slice D) ---
TOP_N = int(os.environ.get("TOP_N", "12"))            # items delivered after ranking
W_SIGNIFICANCE = float(os.environ.get("W_SIGNIFICANCE", "0.5"))
W_RELEVANCE = float(os.environ.get("W_RELEVANCE", "0.3"))
W_NOVELTY = float(os.environ.get("W_NOVELTY", "0.2"))

# --- Digest assembly (Phase 4) ---
DIGEST_DIR = os.environ.get("DIGEST_DIR", "./digests")   # where daily .md files are written


def require_api_key() -> str:
    """Return the Anthropic API key, or fail loudly if it's missing.

    Failing early with a clear message beats a confusing 401 from the API later.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and "
            "fill in your real key (get one at https://console.anthropic.com/)."
        )
    return ANTHROPIC_API_KEY
