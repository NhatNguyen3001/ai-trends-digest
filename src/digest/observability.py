"""Observability: structured logging, a config preflight, and the LangSmith
tracing gate. All best-effort except preflight's one deliberate hard-fail.
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from langsmith import traceable  # re-exported; safe no-op when tracing is disabled

from digest import config

_configured = False


def setup_logging() -> logging.Logger:
    """Configure the root logger once: console (stderr) + a per-run file handler
    under ``config.LOG_DIR``. Idempotent — safe to call from every entry script.
    """
    global _configured
    root = logging.getLogger()
    if _configured:
        return root
    root.setLevel(config.LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        log_dir = Path(config.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fh = logging.FileHandler(log_dir / f"{stamp}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as exc:  # noqa: BLE001 — file logging is best-effort
        root.warning("file logging unavailable (%s); console only.", exc)
    _configured = True
    return root


def preflight() -> None:
    """Validate configuration at startup. Hard-fail on the one thing the run truly
    needs (the Anthropic key); log a visible WARNING for each optional capability
    whose key is absent, so a degraded run is never silent.
    """
    log = logging.getLogger(__name__)
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — the pipeline cannot run. "
            "Copy .env.example to .env and add your key.")
    if not config.VOYAGE_API_KEY:
        log.warning("VOYAGE_API_KEY not set — dedup + cross-day memory disabled.")
    if not config.TAVILY_API_KEY:
        log.warning("TAVILY_API_KEY not set — deep-dive disabled.")
    if not getattr(config, "LANGSMITH_API_KEY", ""):
        log.warning("LANGSMITH_API_KEY not set — tracing disabled.")
    if not config.EMAIL_ENABLED:
        log.warning("email delivery not configured — digest will be saved to file only.")


def configure_tracing() -> bool:
    """Enable LangSmith tracing iff a key is configured AND LANGCHAIN_TRACING_V2 is
    "true" (both from .env). Sets the env vars LangGraph and ``@traceable`` read.
    Returns whether tracing is on. No key / flag off -> a no-op."""
    if not config.LANGSMITH_API_KEY or config.LANGCHAIN_TRACING_V2.lower() != "true":
        return False
    os.environ["LANGSMITH_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = config.LANGSMITH_PROJECT
    logging.getLogger(__name__).info("LangSmith tracing enabled (project=%s).",
                                     config.LANGSMITH_PROJECT)
    return True
