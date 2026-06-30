"""OpenReview significance lookup — a peer-review signal for papers.

Searches OpenReview by title and, when the paper actually went through a reviewed
venue (ICLR/NeurIPS/...), returns its venue, accept/reject decision, and a
best-effort average reviewer rating. Fresh arXiv preprints usually only have a
DBLP/CoRR mirror record (no reviews) -> we return None. Stdlib HTTP only; every
network/parse error soft-fails to None.

This module is the deterministic 'tool'; significance.py hands it to Claude.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass

_BASE = "https://api2.openreview.net"
_SEARCH = f"{_BASE}/notes/search"
_NOTES = f"{_BASE}/notes"


@dataclass
class OpenReviewResult:
    venue: str
    decision: str
    avg_rating: float | None
    num_reviews: int


def _get_json(url: str) -> dict:
    """Single HTTP seam (monkeypatched in tests)."""
    req = urllib.request.Request(url, headers={"User-Agent": "ai-trends-digest"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _cval(note: dict, key: str) -> str:
    """content[key].value (API v2), tolerating a flat string (v1)."""
    c = note.get("content", {}).get(key)
    if isinstance(c, dict):
        return str(c.get("value", ""))
    return str(c) if c is not None else ""


def _decision_from_venue(venue: str) -> str:
    v = venue.lower()
    if "withdraw" in v:
        return "withdrawn"
    if "reject" in v:
        return "rejected"
    if "submitted" in v:
        return "under review"
    if "oral" in v:
        return "accepted (oral)"
    if "spotlight" in v:
        return "accepted (spotlight)"
    if "poster" in v:
        return "accepted (poster)"
    return "accepted" if venue else "unknown"


def _parse_rating(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    m = re.match(r"\s*(\d+)", str(value))
    return float(m.group(1)) if m else None


def _avg_rating(forum: str):
    """Best-effort average of numeric review ratings on the forum. (None, 0) on any miss."""
    try:
        data = _get_json(f"{_NOTES}?forum={urllib.parse.quote(forum)}")
        ratings = []
        for note in data.get("notes", []):
            rv = note.get("content", {}).get("rating")
            val = rv.get("value") if isinstance(rv, dict) else rv
            if val is None:
                continue
            parsed = _parse_rating(val)
            if parsed is not None:
                ratings.append(parsed)
        if not ratings:
            return None, 0
        return sum(ratings) / len(ratings), len(ratings)
    except Exception:  # noqa: BLE001 — rating is best-effort
        return None, 0


def _pick_reviewed_note(notes: list, title: str):
    """First non-mirror note from a real venue whose title matches; else None."""
    want = _norm_title(title)
    for note in notes:
        venueid = _cval(note, "venueid")
        venue = _cval(note, "venue")
        if not venue or venueid.startswith("dblp.org"):
            continue                                   # mirror / no real venue
        if _norm_title(_cval(note, "title")) == want:
            return note
    return None


def lookup_openreview(title: str) -> OpenReviewResult | None:
    """Reviewed-venue record for ``title``, or None (mirror-only / not found / error)."""
    try:
        data = _get_json(f"{_SEARCH}?term={urllib.parse.quote(title)}&limit=10")
        note = _pick_reviewed_note(data.get("notes", []), title)
        if note is None:
            return None
        venue = _cval(note, "venue")
        forum = note.get("forum") or note.get("id") or ""
        avg, n = _avg_rating(forum)
        return OpenReviewResult(venue=venue, decision=_decision_from_venue(venue),
                                avg_rating=avg, num_reviews=n)
    except Exception as exc:  # noqa: BLE001 — soft-fail by design
        print(f"[openreview] lookup failed ({exc})", file=sys.stderr)
        return None
