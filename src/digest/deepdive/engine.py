"""The public entry point for the deep-dive engine.

``deep_dive(item)`` builds the graph, runs it from a fresh initial state, and
returns the final write-up. Any failure — missing key, Tavily/LLM error, graph
blow-up — soft-fails to ``""`` so the digest is never lost to a bad deep-dive.
"""
import sys

from digest.deepdive.graph import build_graph
from digest.deepdive.search import web_search
from digest.llm import get_client
from digest.models import Item


def _initial_state(item: Item) -> dict:
    """A clean starting state: the item plus empty accumulators and zeroed budget."""
    return {
        "item": item,
        "subquestions": [],
        "docs": [],
        "graded_docs": [],
        "draft": "",
        "searches_used": 0,
        "iterations": 0,
        "enough": False,
        "good": False,
    }


def deep_dive(item: Item, *, client_factory=get_client, search_fn=web_search) -> str:
    """Research ``item`` on the web and return a cited write-up (``""`` on failure)."""
    try:
        graph = build_graph(client_factory=client_factory, search_fn=search_fn)
        final = graph.invoke(_initial_state(item))
        return final.get("draft", "")
    except Exception as exc:  # noqa: BLE001 — deep-dive is best-effort
        print(f"[deepdive] deep_dive failed ({type(exc).__name__}: {exc}); "
              "returning empty.", file=sys.stderr)
        return ""
