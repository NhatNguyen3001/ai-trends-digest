"""The deep-dive graph's nodes, as factories.

Each ``make_*`` returns a plain ``fn(state) -> dict`` (a partial state update).
The factory pattern lets tests inject a fake ``client_factory``/``search_fn`` so
no node touches the network or the real API during tests.

Reasoning nodes call the existing ``anthropic`` client directly (``client.messages
.create``) — LangGraph is orchestration only, never an LLM wrapper.
"""
from digest import config


def _ask(client_factory, system: str, user: str, *, max_tokens: int = 1024) -> str:
    """One Claude turn -> its text. Kept tiny so every node reads the same way."""
    client = client_factory()
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


_DECOMPOSE_SYSTEM = (
    "You break a topic into focused research sub-questions for a web search. "
    "Output ONE sub-question per line, no numbering, no preamble."
)


def make_decompose(client_factory):
    """Node: topic -> up to DEEP_DIVE_SUBQUESTIONS search angles."""
    def decompose(state) -> dict:
        item = state["item"]
        user = (
            f"Title: {item.title}\n"
            f"Summary: {item.summary}\n\n"
            f"Write up to {config.DEEP_DIVE_SUBQUESTIONS} research sub-questions that, "
            "answered from the web, would let you write a deeper, cited explainer."
        )
        text = _ask(client_factory, _DECOMPOSE_SYSTEM, user, max_tokens=400)
        subs = [line.strip() for line in text.splitlines() if line.strip()]
        return {"subquestions": subs[: config.DEEP_DIVE_SUBQUESTIONS]}
    return decompose


def make_retrieve(search_fn):
    """Node: run one web search per sub-question, collect the snippets.

    Counts one search per query against the budget (``searches_used``).
    """
    def retrieve(state) -> dict:
        docs = list(state["docs"])
        used = state["searches_used"]
        for q in state["subquestions"]:
            docs.extend(search_fn(q, max_results=5))
            used += 1
        return {"docs": docs, "searches_used": used}
    return retrieve


_SYNTHESISE_SYSTEM = (
    "You write a concise, well-structured explainer for an AI engineer, grounded "
    "ONLY in the provided sources. Cite claims inline as [n] referring to the "
    "numbered sources, and end with a 'Sources' list. No hype; say plainly if the "
    "sources are thin."
)


def _format_docs(docs: list[dict]) -> str:
    """Number the docs so the model can cite them as [1], [2], ..."""
    return "\n\n".join(
        f"[{i}] {d.get('title', '')} ({d.get('url', '')})\n{d.get('text', '')}"
        for i, d in enumerate(docs, start=1)
    )


def make_synthesise(client_factory):
    """Node: turn the (graded) docs into the cited write-up."""
    def synthesise(state) -> dict:
        # Prefer graded docs (slice 2+); before grading exists, fall back to all docs.
        docs = state["graded_docs"] or state["docs"]
        item = state["item"]
        user = (
            f"Topic: {item.title}\n\n"
            f"Sources:\n{_format_docs(docs)}\n\n"
            "Write the explainer, citing sources inline as [n]."
        )
        text = _ask(client_factory, _SYNTHESISE_SYSTEM, user, max_tokens=1500)
        return {"draft": text}
    return synthesise
