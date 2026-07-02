"""On-demand deep-dive: deepen chosen items from an already-generated digest.

Usage:
    python scripts/deep_dive.py 3 7                 # deepen items #3 and #7 of the latest digest
    python scripts/deep_dive.py --digest 2026-07-02_09-30-00 3

The daily run (`scripts/run_digest.py`) writes a JSON sidecar next to each digest.
This script reloads it, runs the agentic deep-dive engine on the item numbers you
pass, re-renders the markdown with those write-ups filled in, prints it, and saves
a `<stamp>_deepdive.md` alongside the original — the pipeline is not re-run.
"""

import sys
from datetime import datetime
from pathlib import Path

# src-layout shim (same as run_digest.py): put src/ on the import path.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from digest import config  # noqa: E402
from digest.assemble import load_digest_data, render_digest  # noqa: E402
from digest.deepdive.engine import deep_dive  # noqa: E402


def run_deep_dive(data: dict, numbers, *, dive_fn=deep_dive) -> str:
    """Set ``deep_dive`` on the chosen (1-based) items and re-render the markdown.

    Pure-ish: takes loaded ``data``, mutates the chosen items in place, and returns
    the re-rendered digest. ``dive_fn`` is injectable so tests skip the real engine.
    """
    items = data["items"]
    for n in numbers:
        if 1 <= n <= len(items):
            item = items[n - 1]
            item.deep_dive = dive_fn(item)
        else:
            print(f"[deep_dive] item #{n} out of range (1..{len(items)}); skipped.",
                  file=sys.stderr)

    run_at = data.get("run_at", "")
    run_dt = datetime.fromisoformat(run_at) if run_at else datetime.now()
    return render_digest(items, data["summaries"], run_dt, data.get("intro", ""))


def _latest_sidecar(directory: Path) -> Path | None:
    """The newest ``*.json`` sidecar in the digest directory, if any."""
    sidecars = sorted(directory.glob("*.json"))
    return sidecars[-1] if sidecars else None


def _parse_args(argv: list[str]) -> tuple[str | None, list[int]]:
    """Split argv into an optional ``--digest <stamp>`` and the item numbers."""
    stamp = None
    numbers: list[int] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--digest" and i + 1 < len(argv):
            stamp = argv[i + 1]
            i += 2
            continue
        numbers.append(int(argv[i]))
        i += 1
    return stamp, numbers


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stamp, numbers = _parse_args(sys.argv[1:])
    directory = Path(config.DIGEST_DIR)

    if stamp:
        sidecar = directory / f"{stamp}.json"
    else:
        sidecar = _latest_sidecar(directory)

    if sidecar is None or not sidecar.exists():
        print(f"[deep_dive] no digest sidecar found in {directory}. Run "
              "scripts/run_digest.py first.", file=sys.stderr)
        sys.exit(1)
    if not numbers:
        print("[deep_dive] give one or more item numbers, e.g. "
              "`python scripts/deep_dive.py 3 7`.", file=sys.stderr)
        sys.exit(1)

    print(f"Deep-diving items {numbers} from {sidecar.name}...\n")
    data = load_digest_data(sidecar)
    markdown = run_deep_dive(data, numbers)
    print(markdown)

    out = sidecar.with_name(sidecar.stem + "_deepdive.md")
    out.write_text(markdown, encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
