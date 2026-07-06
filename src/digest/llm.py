"""Anthropic client, created in one place.

Centralising client creation means every part of the app talks to Claude the
same way. When we later add retries, tracing (LangSmith), or model routing,
we change it here once instead of in every caller.
"""

import anthropic
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from langsmith.wrappers import wrap_anthropic

from digest import config


def get_client() -> anthropic.Anthropic:
    """Build an Anthropic client using the key from config (fails loud if missing).

    ``wrap_anthropic`` instruments each ``messages.create`` call as a LangSmith LLM
    run (model + token usage -> call counts + cost). It's a no-op passthrough when
    tracing is disabled, so tests and offline runs are unaffected.
    """
    return wrap_anthropic(anthropic.Anthropic(api_key=config.require_api_key(),
                                               max_retries=config.ANTHROPIC_MAX_RETRIES))


@traceable(run_type="llm", name="ChatAnthropic")
def parse_message(client, **kwargs):
    """Run ``client.messages.parse(...)`` and return the validated ``parsed_output``,
    recorded as a LangSmith LLM run carrying token usage + cost.

    ``wrap_anthropic`` instruments ``messages.create`` but NOT ``messages.parse``, so
    without this the structured-output stages (ranking, tagging) would report no tokens
    or cost. Returning the clean parsed model (not the raw response) also keeps the run's
    outputs tidy — serializing the full Anthropic response spams pydantic warnings.
    Passthrough when tracing is off: ``get_current_run_tree()`` is None and usage is
    never touched.
    """
    resp = client.messages.parse(**kwargs)
    rt = get_current_run_tree()
    if rt is not None:                       # None when tracing is off (tests/offline)
        u = resp.usage
        rt.set(
            metadata={"ls_provider": "anthropic",
                      "ls_model_name": kwargs.get("model", "")},
            usage_metadata={"input_tokens": u.input_tokens,
                            "output_tokens": u.output_tokens,
                            "total_tokens": u.input_tokens + u.output_tokens},
        )
    return resp.parsed_output
