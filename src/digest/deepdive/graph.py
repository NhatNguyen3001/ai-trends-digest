"""Assemble the deep-dive nodes into a compiled LangGraph.

Slice 2 adds the CRAG loop:
    decompose -> retrieve -> grade -> (route)
                                       |-> correct -> retrieve   (weak, budget left)
                                       |-> synthesise -> END      (enough, or budget spent)

The router (`route_after_grade`) is where the budget/early-exit controller lives:
it forces the graph forward once the search/iteration caps are hit so the cycle
can never spin forever.

``build_graph`` takes the ``client_factory``/``search_fn`` seams so tests build a
graph wired to fakes — the compiled graph never reaches for the network or a key.
"""
from langgraph.graph import StateGraph, START, END

from digest import config
from digest.deepdive.state import DeepDiveState
from digest.deepdive import nodes
from digest.deepdive.search import web_search
from digest.llm import get_client


def route_after_grade(state) -> str:
    """Decide where to go after grading: keep researching, or write.

    - Have relevant docs (`enough`)  -> synthesise.
    - Out of budget (searches/iters) -> synthesise anyway (early-exit).
    - Otherwise                      -> correct (reword + retry).
    """
    if state["enough"]:
        return "synthesise"
    if (state["searches_used"] >= config.DEEP_DIVE_MAX_SEARCHES
            or state["iterations"] >= config.DEEP_DIVE_MAX_ITERS):
        return "synthesise"
    return "correct"


def build_graph(*, client_factory=get_client, search_fn=web_search):
    """Wire and compile the deep-dive graph (with the CRAG grade/correct loop)."""
    g = StateGraph(DeepDiveState)
    g.add_node("decompose", nodes.make_decompose(client_factory))
    g.add_node("retrieve", nodes.make_retrieve(search_fn))
    g.add_node("grade", nodes.make_grade(client_factory))
    g.add_node("correct", nodes.make_correct(client_factory))
    g.add_node("synthesise", nodes.make_synthesise(client_factory))

    g.add_edge(START, "decompose")
    g.add_edge("decompose", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route_after_grade,
                            {"correct": "correct", "synthesise": "synthesise"})
    g.add_edge("correct", "retrieve")
    g.add_edge("synthesise", END)
    return g.compile()
