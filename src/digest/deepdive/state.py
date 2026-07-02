"""The shared state the deep-dive graph threads through its nodes.

LangGraph passes one dict-like state between nodes; each node returns a *partial*
update that LangGraph merges in. Using a ``TypedDict`` documents the keys and lets
editors catch typos, while staying a plain dict at runtime.
"""
from typing import TypedDict

from digest.models import Item


class DeepDiveState(TypedDict):
    item: Item                  # the digest item being researched
    subquestions: list[str]     # decompose -> the angles to search
    docs: list[dict]            # retrieve -> {title, url, text} snippets found
    graded_docs: list[dict]     # grade (slice 2) -> the docs kept as relevant
    draft: str                  # synthesise -> the final cited write-up
    searches_used: int          # budget counter: total Tavily queries run
    iterations: int             # budget counter: corrective/reflective passes
