"""Phase 1 entry point: fetch arXiv -> summarise -> print.

Run it with:  python scripts/run_digest.py

This is the first end-to-end slice of the pipeline: one source flows all the way
through the LLM to a printed digest. No ranking, dedup, or async yet.
"""

import sys
from datetime import date
from pathlib import Path

# src-layout shim (same as scripts/hello.py): put src/ on the import path so we
# can `import digest`. Goes away once we switch to an editable install.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from digest.collectors import collect_all  # noqa: E402 (after path setup)
from digest.dedup import dedup_within_day  # noqa: E402
from digest.summarise import summarise_items  # noqa: E402


def main() -> None:
    # Windows consoles default to cp1252 and choke on Unicode; force UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Collecting from all sources (arXiv, RSS, Anthropic, GitHub)...")
    items = collect_all()
    raw_count = len(items)

    print(f"Collected {raw_count} items. De-duplicating...")
    items = dedup_within_day(items)
    print(f"{raw_count} raw -> {len(items)} after dedup. Summarising with Claude...\n")

    summaries = summarise_items(items)

    print(f"# AI Trends Digest — {date.today():%Y-%m-%d}\n")
    for rank, (item, summary) in enumerate(zip(items, summaries), start=1):
        print(f"{rank}. [{item.source}] {item.title}")
        print(f"   {summary}")
        print(f"   {item.url}")
        if item.merged_sources:
            print(f"   also covered by: {', '.join(item.merged_sources)}")
        print()


if __name__ == "__main__":
    main()
