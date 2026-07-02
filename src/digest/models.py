"""The common item schema shared across the whole pipeline.

Every source — arXiv now; GitHub, news, and RSS in Phase 2 — normalises its raw
results into this one ``Item`` shape. Everything downstream (summarise, rank,
dedup, deliver) only ever deals with ``Item``, never a source's raw format.
One shared contract keeps the rest of the code source-agnostic.

We use a plain ``@dataclass`` here (standard library, zero dependencies). When
Phase 3 needs validation of messy multi-source data and structured LLM outputs,
we'll likely move this to Pydantic — a near-mechanical change.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Tag:
    """A typed entity/topic extracted from an item, for cross-reference grouping.

    ``type`` is one of: "model", "org", "technique", "dataset", "task".
    """

    name: str
    type: str


@dataclass
class Item:
    """One normalised thing the digest knows about (a paper, repo, article...)."""

    source: str            # which collector produced it, e.g. "arxiv"
    id: str                # stable id *within* that source, e.g. "2401.12345v1"
    title: str
    url: str               # canonical link a human can open
    published: datetime    # timezone-aware (arXiv gives UTC)
    summary: str           # the source's own text (for arXiv: the abstract)

    # authors defaults to an empty list. We use field(default_factory=list)
    # rather than `authors: list[str] = []` because a bare [] would be shared
    # across every Item instance — a classic Python mutable-default bug.
    authors: list[str] = field(default_factory=list)

    # Filled by dedup: "source: url" of other items merged into this one as
    # duplicates (same story from another source). Empty when nothing merged.
    merged_sources: list[str] = field(default_factory=list)

    # Filled by ranking (slice D): the blended 0-10 score and the one-line "why".
    score: float = 0.0
    score_reason: str = ""

    # Filled by the OpenReview tool (slice E): a one-line peer-review note for papers.
    significance_note: str = ""

    # Filled by tagging (slice F): typed entities for cross-reference grouping.
    tags: list[Tag] = field(default_factory=list)

    # Filled by the deep-dive engine (Phase 5): a cited, web-researched write-up.
    deep_dive: str = ""
