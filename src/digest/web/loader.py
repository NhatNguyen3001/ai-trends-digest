"""Find and load digest sidecars off disk, as view models."""
import logging
from datetime import datetime
from pathlib import Path

from digest import config
from digest.assemble import load_digest_data, save_digest_data
from digest.deepdive.engine import deep_dive
from digest.web.view import build_view, build_archive_row, ArchiveRow, DigestView

_log = logging.getLogger(__name__)


def all_digest_paths(dirpath=None) -> list[Path]:
    """Every digest JSON, newest-first (stems are YYYY-MM-DD_HH-MM-SS)."""
    d = Path(dirpath or config.DIGEST_DIR)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"), key=lambda p: p.stem, reverse=True)


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
