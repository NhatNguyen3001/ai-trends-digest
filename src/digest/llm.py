"""Anthropic client, created in one place.

Centralising client creation means every part of the app talks to Claude the
same way. When we later add retries, tracing (LangSmith), or model routing,
we change it here once instead of in every caller.
"""

import anthropic

from digest import config


def get_client() -> anthropic.Anthropic:
    """Build an Anthropic client using the key from config (fails loud if missing)."""
    return anthropic.Anthropic(api_key=config.require_api_key())
