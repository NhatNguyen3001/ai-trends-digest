"""The saved / read-later pin store (Phase 7 slice 4).

A pin is a *snapshot* of an item's display data, keyed by sha1(url), persisted to a
single JSON file (config.PINS_PATH). The store is core (not web) so a later taste
blend can read it. All functions default their path to config.PINS_PATH.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from digest import config
from digest.assemble import _item_to_dict
from digest.models import Item

_log = logging.getLogger(__name__)


def pin_key(url: str) -> str:
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()


def _path(path=None) -> Path:
    return Path(path or config.PINS_PATH)


def load_pins(path=None) -> list[dict]:
    """All pins, newest-first. Missing or corrupt file -> []."""
    p = _path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pins = data.get("pins", []) if isinstance(data, dict) else data
        return list(reversed(pins))                       # stored oldest-first
    except Exception as e:                                # noqa: BLE001
        _log.warning("could not read pins file %s: %s", p, e)
        return []


def _write(pins_oldest_first: list[dict], path=None) -> None:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pins": pins_oldest_first}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def is_pinned(url, path=None) -> bool:
    key = pin_key(url)
    return any(rec["key"] == key for rec in load_pins(path))


def pinned_keys(path=None) -> set:
    return {rec["key"] for rec in load_pins(path)}


def add_pin(item: Item, summary: str, from_stamp="", path=None) -> dict:
    """Idempotent per url. Returns the (existing or new) pin record."""
    key = pin_key(item.url)
    stored = list(reversed(load_pins(path)))              # back to oldest-first
    for rec in stored:
        if rec["key"] == key:
            return rec
    rec = {
        "key": key,
        "item": _item_to_dict(item),
        "summary": summary,
        "pinned_at": datetime.now(timezone.utc).isoformat(),
        "from_stamp": from_stamp,
    }
    stored.append(rec)
    _write(stored, path)
    return rec


def remove_pin(key: str, path=None) -> bool:
    """Drop the pin with this key. Returns whether it existed."""
    stored = list(reversed(load_pins(path)))
    kept = [r for r in stored if r["key"] != key]
    if len(kept) == len(stored):
        return False
    _write(kept, path)
    return True


def filter_pins(pins: list[dict], type=None, tag=None, source=None) -> list[dict]:
    """Pure filter over pin records by tag-type / tag-name / source (all optional, AND-ed)."""
    def ok(rec):
        it = rec.get("item", {})
        tags = it.get("tags", [])
        if source and it.get("source") != source:
            return False
        if type and not any(t.get("type") == type for t in tags):
            return False
        if tag and not any(t.get("name") == tag for t in tags):
            return False
        return True
    return [r for r in pins if ok(r)]
