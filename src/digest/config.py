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
# "GitHub Active" lens: established repos (>= this many stars) pushed within N days.
GITHUB_ACTIVE_DAYS = int(os.environ.get("GITHUB_ACTIVE_DAYS", "14"))
GITHUB_MIN_STARS = int(os.environ.get("GITHUB_MIN_STARS", "5000"))

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
QDRANT_URL = os.environ.get("QDRANT_URL", "")   # set in Docker -> use the Qdrant service; "" -> embedded
MEMORY_DAYS = int(os.environ.get("MEMORY_DAYS", "14"))        # rolling window length
CROSS_SUPPRESS = float(os.environ.get("CROSS_SUPPRESS", "0.93"))  # >= -> drop (old news)
CROSS_UPDATE = float(os.environ.get("CROSS_UPDATE", "0.85"))      # >= -> mark "Update:"

# Quiet-day recaps (Phase 6): when fewer than QUIET_DAY_MIN fresh items are
# delivered, append QUIET_DAY_RECAPS random past-delivered items as "Worth revisiting".
QUIET_DAY_MIN = int(os.environ.get("QUIET_DAY_MIN", "5"))
QUIET_DAY_RECAPS = int(os.environ.get("QUIET_DAY_RECAPS", "3"))

# --- Ranking (slice D) ---
TOP_N = int(os.environ.get("TOP_N", "20"))            # max items delivered (a ceiling, not a quota)
W_SIGNIFICANCE = float(os.environ.get("W_SIGNIFICANCE", "0.5"))
W_RELEVANCE = float(os.environ.get("W_RELEVANCE", "0.3"))
W_NOVELTY = float(os.environ.get("W_NOVELTY", "0.2"))

# --- Delivery balancing (Phase 4.5) ---
# Per-source-type caps stop any one bucket (papers especially) from dominating the
# top-N, and the score floor keeps below-bar filler out (so TOP_N is a ceiling).
CAP_PAPER = int(os.environ.get("CAP_PAPER", "8"))               # arXiv
CAP_REPO_TRENDING = int(os.environ.get("CAP_REPO_TRENDING", "5"))  # GitHub (trending)
CAP_REPO_ACTIVE = int(os.environ.get("CAP_REPO_ACTIVE", "3"))      # GitHub Active (established)
CAP_NEWS = int(os.environ.get("CAP_NEWS", "10"))                # RSS + Anthropic scrapers
SCORE_FLOOR = float(os.environ.get("SCORE_FLOOR", "4.0"))  # min blended score to deliver

# --- Digest assembly (Phase 4) ---
DIGEST_DIR = os.environ.get("DIGEST_DIR", "./digests")   # where daily .md files are written

# --- Saved / pins (Phase 7 slice 4) ---
PINS_PATH = os.environ.get("PINS_PATH", "./data/pins.json")  # saved/read-later library (git-ignored)

# --- Email delivery (Phase 9 sub-project A) ---
# Gmail locally (needs an APP PASSWORD, not your account password); the same SMTP
# path points at SES's SMTP endpoint in the cloud — only these values change.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))          # SSL
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "") or SMTP_USER   # defaults to the SMTP user
EMAIL_TO = os.environ.get("EMAIL_TO", "")
# Send only when fully configured; otherwise the run is file-only (as today).
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and EMAIL_TO)

# --- Observability (Phase 6 harness hardening) ---
LOG_DIR = os.environ.get("LOG_DIR", "./logs")     # per-run .log files (git-ignored)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

RETRY_ATTEMPTS = int(os.environ.get("RETRY_ATTEMPTS", "3"))
RETRY_BASE_DELAY = float(os.environ.get("RETRY_BASE_DELAY", "1.0"))
ANTHROPIC_MAX_RETRIES = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "4"))

# LangSmith tracing is OPTIONAL: blank key -> tracing stays off (no external calls).
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "ai-trends-digest")
# Tracing on/off flag, read straight from .env (LangGraph + @traceable read this env
# var by name). Anything but "true" -> off. configure_tracing() also gates on the API
# key, so tracing needs BOTH a key and this flag set to "true".
LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "true")

# --- Over-collect depth (Phase 6) ---
# Fetch a deep bench, not a shortlist. Delivery is still bounded by TOP_N + source
# caps + SCORE_FLOOR, so raising these only widens the pool the curator/ranker use.
ARXIV_MAX = int(os.environ.get("ARXIV_MAX", "25"))
GITHUB_MAX = int(os.environ.get("GITHUB_MAX", "25"))   # both github and github_active

# --- Deep-dive engine (Phase 5) ---
# Tavily is a soft dependency: blank key -> a deep-dive degrades to "" (the digest
# still renders). The two caps bound the corrective/reflective loops (budget/early-exit).
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
DEEP_DIVE_SUBQUESTIONS = int(os.environ.get("DEEP_DIVE_SUBQUESTIONS", "3"))
DEEP_DIVE_MAX_SEARCHES = int(os.environ.get("DEEP_DIVE_MAX_SEARCHES", "6"))
DEEP_DIVE_MAX_ITERS = int(os.environ.get("DEEP_DIVE_MAX_ITERS", "3"))


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
