"""The 'hello agent' — one real Claude API call.

This is intentionally tiny. Its only job is to prove the whole chain works:
environment -> SDK -> API key -> model -> a real sentence back. Once this runs,
we know the foundation is solid and can build the actual pipeline on top.
"""

import anthropic

from digest import config


def say_hello() -> str:
    """Ask Claude for a one-sentence greeting and return its text."""
    # The SDK reads ANTHROPIC_API_KEY from the environment by default, but we
    # pass it explicitly (via config) so all settings flow through one place.
    client = anthropic.Anthropic(api_key=config.require_api_key())

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=256,  # deliberately small — we only want one short sentence
        messages=[
            {
                "role": "user",
                "content": (
                    "In one friendly sentence, confirm you're working and "
                    "introduce yourself as the engine behind an AI trends "
                    "daily digest."
                ),
            }
        ],
    )

    # response.content is a list of content blocks. For a plain reply there's
    # one block of type "text"; we pull its text out.
    for block in response.content:
        if block.type == "text":
            return block.text

    return "(no text returned)"
