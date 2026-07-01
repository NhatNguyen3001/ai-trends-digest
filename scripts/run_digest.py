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
from digest.curate import curate, remember_kept  # noqa: E402
from digest.ranking import rank_items  # noqa: E402
from digest.significance import enrich_significance  # noqa: E402
from digest.tagging import tag_items  # noqa: E402
from digest.assemble import write_intro, render_digest, write_digest_file  # noqa: E402
from digest.memory_store import get_store  # noqa: E402
from digest.summarise import summarise_items  # noqa: E402
from digest import config  # noqa: E402


def main() -> None:
    # Windows consoles default to cp1252 and choke on Unicode; force UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Collecting from all sources (arXiv, RSS, Anthropic, GitHub)...")
    items = collect_all()
    raw_count = len(items)

    # Open cross-day memory (best-effort: a store failure must not stop the digest).
    try:
        store = get_store(config.QDRANT_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[run] memory unavailable ({exc}); running without cross-day.")
        store = None

    print(f"Collected {raw_count} items. Curating (dedup + cross-day memory)...")
    result = curate(items, store=store)
    curated = result.items
    print(f"{raw_count} raw -> {len(curated)} curated "
          f"({result.suppressed} suppressed, {result.updated} marked Update). "
          f"Ranking...")

    items = rank_items(curated, top_n=config.TOP_N)
    print(f"{len(curated)} curated -> {len(items)} delivered (top {config.TOP_N}). "
          f"Checking OpenReview for papers...")
    enrich_significance(items)

    print("Tagging items for cross-reference...")
    tag_items(items)

    print("Summarising with Claude...\n")
    summaries = summarise_items(items)

    print("Writing the day's intro...\n")
    intro = write_intro(items)
    markdown = render_digest(items, summaries, date.today(), intro)
    print(markdown)

    try:
        path = write_digest_file(markdown, date.today())
        print(f"wrote {path}")
    except Exception as exc:  # noqa: BLE001 — digest already printed; don't lose the run
        print(f"[run] could not write digest file ({exc}); printed above only.",
              file=sys.stderr)

    # Write today's survivors back to memory AFTER delivery, then prune.
    remember_kept(result, store=store, run_date=date.today())


if __name__ == "__main__":
    main()
