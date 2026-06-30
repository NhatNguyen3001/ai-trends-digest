"""Agentic significance enrichment: Claude calls the OpenReview tool.

For each top-ranked arXiv paper, run a manual Claude tool-use loop. Claude is given
one tool (lookup_openreview); it calls the tool, reads the peer-review result, and
writes a one-sentence grounded note, which we store on item.significance_note.
Annotate-only — it never changes ranking. Per-item soft-fail: a failed lookup or
API error leaves that note empty and the run continues.
"""

import sys

from digest import config
from digest.llm import get_client
from digest.openreview import lookup_openreview

_TOOL = {
    "name": "lookup_openreview",
    "description": (
        "Look up a paper's peer-review outcome on OpenReview by its exact title. "
        "Returns the venue, accept/reject decision, and average reviewer rating, or "
        "reports that no reviewed OpenReview record exists for the title."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"title": {"type": "string", "description": "The paper title"}},
        "required": ["title"],
    },
}


def _result_text(result) -> str:
    if result is None:
        return "No reviewed OpenReview record found for this title."
    rating = (f", average reviewer rating {result.avg_rating:.1f}"
              if result.avg_rating is not None else "")
    return (f"Found on OpenReview: venue '{result.venue}', decision {result.decision}"
            f"{rating} ({result.num_reviews} reviews).")


def _significance_note(title, *, client, lookup_fn) -> str:
    """Run the tool-use loop for one title; return Claude's one-sentence note."""
    messages = [{
        "role": "user",
        "content": (
            f'Assess the peer-review significance of this paper:\n\n"{title}"\n\n'
            "Use the lookup_openreview tool, then state in ONE sentence whether it was "
            "peer-reviewed/accepted and at what venue (include the rating if available), "
            "or that no peer-review record was found. Be concrete; do not speculate "
            "beyond the tool result."
        ),
    }]

    for _ in range(3):  # loop guard
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=500, tools=[_TOOL], messages=messages)
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for b in response.content:
            if b.type == "tool_use" and b.name == "lookup_openreview":
                result = lookup_fn(b.input.get("title", title))
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": _result_text(result)})
        messages.append({"role": "user", "content": results})

    return ""  # loop exhausted -> no note


def enrich_significance(items, *, client_factory=get_client, lookup_fn=lookup_openreview) -> None:
    """Annotate each arXiv paper in ``items`` with a peer-review significance note."""
    client = None
    for it in items:
        if it.source != "arxiv":
            continue                                   # OpenReview only indexes papers
        try:
            if client is None:
                client = client_factory()
            it.significance_note = _significance_note(it.title, client=client,
                                                      lookup_fn=lookup_fn)
        except Exception as exc:  # noqa: BLE001 — per-item soft-fail
            print(f"[significance] enrich failed for {it.title!r} ({exc})", file=sys.stderr)
