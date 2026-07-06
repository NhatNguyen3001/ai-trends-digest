"""Find and load the newest digest sidecar off disk, as a DigestView."""
from pathlib import Path

from digest import config
from digest.assemble import load_digest_data
from digest.web.view import build_view, DigestView


def latest_digest_path(dirpath=None) -> Path | None:
    d = Path(dirpath or config.DIGEST_DIR)
    if not d.exists():
        return None
    files = sorted(d.glob("*.json"))     # names are YYYY-MM-DD_HH-MM-SS -> lexical == chronological
    return files[-1] if files else None


def load_view_model(path) -> DigestView:
    return build_view(load_digest_data(path))
