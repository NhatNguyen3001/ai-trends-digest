"""Find and load digest sidecars off disk, as view models."""
import logging
import re
from datetime import datetime
from pathlib import Path

# Digest sidecars are named YYYY-MM-DD_HH-MM-SS.json. Match only those so a stray
# .json in the digest dir (e.g. a co-located pins file) is never read as a digest.
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")

from digest import config
from digest.assemble import load_digest_data, save_digest_data
from digest.deepdive.engine import deep_dive
from digest.pins import add_pin, load_pins, filter_pins
from digest.web.view import build_view, build_archive_row, build_saved_view, ArchiveRow, DigestView

_log = logging.getLogger(__name__)


def all_digest_paths(dirpath=None) -> list[Path]:
    """Every digest JSON, newest-first (stems are YYYY-MM-DD_HH-MM-SS)."""
    d = Path(dirpath or config.DIGEST_DIR)
    if not d.exists():
        return []
    stamped = [p for p in d.glob("*.json") if _STAMP_RE.match(p.stem)]
    return sorted(stamped, key=lambda p: p.stem, reverse=True)


def latest_digest_path(dirpath=None) -> Path | None:
    paths = all_digest_paths(dirpath)
    return paths[0] if paths else None


def digest_path_for(stamp, dirpath=None) -> Path | None:
    """Resolve a run stamp (file stem) to its Path; None if no such file.

    Matches against known stems only, so path-traversal strings never resolve.
    """
    for p in all_digest_paths(dirpath):
        if p.stem == stamp:
            return p
    return None


def neighbors(stamp, dirpath=None) -> tuple[str | None, str | None]:
    """(newer_stamp, older_stamp) for a stamp in newest-first order; (None, None) if unknown."""
    stems = [p.stem for p in all_digest_paths(dirpath)]
    if stamp not in stems:
        return (None, None)
    i = stems.index(stamp)
    newer = stems[i - 1] if i > 0 else None
    older = stems[i + 1] if i + 1 < len(stems) else None
    return (newer, older)


def load_archive(dirpath=None) -> list[ArchiveRow]:
    """Rich archive rows, newest-first. A single corrupt file is skipped, not fatal."""
    rows = []
    for p in all_digest_paths(dirpath):
        try:
            rows.append(build_archive_row(p.stem, load_digest_data(p)))
        except Exception as e:            # noqa: BLE001 - one bad file must not blank the list
            _log.warning("skipping unreadable digest %s: %s", p.name, e)
    return rows


def load_view_model(path) -> DigestView:
    return build_view(load_digest_data(path))


def run_item_deepdive(stamp, index, dirpath=None, dive_fn=None):
    """Run (or serve cached) the deep-dive for item #index (1-based) of a digest.

    Returns the item's ItemView with deep_dive_html populated, or None if the stamp
    or index does not resolve. dive_fn defaults to the real engine; injected in tests.
    """
    if dive_fn is None:
        dive_fn = deep_dive
    path = digest_path_for(stamp, dirpath)
    if path is None:
        return None
    data = load_digest_data(path)
    items = data["items"]
    if not (1 <= index <= len(items)):
        return None
    item = items[index - 1]
    if not item.deep_dive:                       # empty/missing -> run; non-empty -> cached
        item.deep_dive = dive_fn(item) or ""
        if item.deep_dive:                       # persist only a real result
            try:
                run_at = data.get("run_at", "")
                run_dt = datetime.fromisoformat(run_at) if run_at else datetime.now()
                save_digest_data(path, items, data["summaries"], data.get("intro", ""),
                                 run_dt, stats=data.get("stats"))
            except Exception as e:               # noqa: BLE001 - persist is best-effort
                _log.warning("could not persist deep-dive for %s #%s: %s", stamp, index, e)
    return build_view(data).items[index - 1]


def add_pin_from(stamp, index, dirpath=None):
    """Snapshot item #index (1-based) of a digest into the pin store. Returns the key or None."""
    path = digest_path_for(stamp, dirpath)
    if path is None:
        return None
    data = load_digest_data(path)
    items, summaries = data["items"], data["summaries"]
    if not (1 <= index <= len(items)):
        return None
    rec = add_pin(items[index - 1], summaries[index - 1] if index - 1 < len(summaries) else "",
                  from_stamp=stamp)
    return rec["key"]


def saved_view(type=None, tag=None, source=None):
    """The saved library as a DigestView, optionally filtered."""
    return build_saved_view(filter_pins(load_pins(), type=type, tag=tag, source=source))


def saved_facets() -> dict:
    """Distinct type/tag/source values across all pins, for the filter bar."""
    types, tags, sources = set(), set(), set()
    for rec in load_pins():
        it = rec.get("item", {})
        sources.add(it.get("source", ""))
        for t in it.get("tags", []):
            types.add(t.get("type", ""))
            tags.add(t.get("name", ""))
    return {"types": sorted(x for x in types if x),
            "tags": sorted(x for x in tags if x),
            "sources": sorted(x for x in sources if x)}
