"""The deep-dive graph's nodes, as factories.

Each ``make_*`` returns a plain ``fn(state) -> dict`` (a partial state update).
The factory pattern lets tests inject a fake ``client_factory``/``search_fn`` so
no node touches the network or the real API during tests.

Reasoning nodes call the existing ``anthropic`` client directly (``client.messages
.create``) — LangGraph is orchestration only, never an LLM wrapper.
"""
import json

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


_GRADE_SYSTEM = (
    "You judge whether each retrieved source is actually relevant and useful for "
    "writing about the topic. Reply with ONLY a JSON object mapping each source's "
    "index (as a string) to true (keep) or false (drop), e.g. "
    '{"0": true, "1": false}. No prose.'
)


def make_grade(client_factory):
    """Node (CRAG): keep only the relevant docs; flag whether we have enough.

    The verdict is asked for as an INDEX-KEYED JSON object (never a positional
    array) — the project's hard rule, so a shifted/short reply can't silently
    misalign which doc got which verdict.
    """
    def grade(state) -> dict:
        docs = state["docs"]
        if not docs:
            return {"graded_docs": [], "enough": False}
        user = (
            f"Topic: {state['item'].title}\n\n"
            f"Sources:\n{_format_docs(docs)}\n\n"
            "Return the keep/drop JSON object."
        )
        text = _ask(client_factory, _GRADE_SYSTEM, user, max_tokens=300)
        try:
            verdict = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            verdict = {}
        kept = [d for i, d in enumerate(docs) if verdict.get(str(i)) is True]
        return {"graded_docs": kept, "enough": len(kept) >= 1}
    return grade


_CORRECT_SYSTEM = (
    "The previous web searches returned weak results. Propose better, reworded "
    "search sub-questions for the topic. ONE per line, no numbering, no preamble."
)


def make_correct(client_factory):
    """Node (CRAG): reword the sub-questions for another retrieval pass.

    Increments ``iterations`` so the budget controller can bound the loop.
    """
    def correct(state) -> dict:
        item = state["item"]
        prior = "\n".join(f"- {q}" for q in state["subquestions"])
        user = (
            f"Topic: {item.title}\nSummary: {item.summary}\n\n"
            f"Previous sub-questions (weak results):\n{prior}\n\n"
            f"Write up to {config.DEEP_DIVE_SUBQUESTIONS} better sub-questions."
        )
        text = _ask(client_factory, _CORRECT_SYSTEM, user, max_tokens=400)
        subs = [line.strip() for line in text.splitlines() if line.strip()]
        return {"subquestions": subs[: config.DEEP_DIVE_SUBQUESTIONS],
                "iterations": state["iterations"] + 1}
    return correct


_REFLECT_SYSTEM = (
    "You are a strict reviewer of a research write-up. Judge whether its claims are "
    "well supported by cited sources and whether it actually answers the topic. "
    "Reply with ONLY one word: 'good' if it is solid, or 'weak' if it needs more "
    "research. No other text."
)


def make_reflect(client_factory):
    """Node (Self-RAG): critique the draft; ``good`` gates one more research pass.

    Increments ``iterations`` (shared budget counter with ``correct``) so the
    reflect loop is bounded by the same caps.
    """
    def reflect(state) -> dict:
        user = (
            f"Topic: {state['item'].title}\n\n"
            f"Draft:\n{state['draft']}\n\n"
            "Is this good or weak?"
        )
        text = _ask(client_factory, _REFLECT_SYSTEM, user, max_tokens=50)
        good = text.strip().lower().startswith("good")
        return {"good": good, "iterations": state["iterations"] + 1}
    return reflect


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
