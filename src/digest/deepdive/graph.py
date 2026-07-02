"""Assemble the deep-dive nodes into a compiled LangGraph.

Slice 1 is a straight line: decompose -> retrieve -> synthesise. Later slices add
a grade node with budget-gated routing (CRAG) and a reflect loop (Self-RAG).

``build_graph`` takes the ``client_factory``/``search_fn`` seams so tests build a
graph wired to fakes — the compiled graph never reaches for the network or a key.
"""
from langgraph.graph import StateGraph, START, END

from digest.deepdive.state import DeepDiveState
from digest.deepdive import nodes
from digest.deepdive.search import web_search
from digest.llm import get_client


def build_graph(*, client_factory=get_client, search_fn=web_search):
    """Wire and compile the linear deep-dive graph."""
    g = StateGraph(DeepDiveState)
    g.add_node("decompose", nodes.make_decompose(client_factory))
    g.add_node("retrieve", nodes.make_retrieve(search_fn))
    g.add_node("synthesise", nodes.make_synthesise(client_factory))

    g.add_edge(START, "decompose")
    g.add_edge("decompose", "retrieve")
    g.add_edge("retrieve", "synthesise")
    g.add_edge("synthesise", END)
    return g.compile()
