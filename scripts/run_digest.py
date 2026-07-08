"""Phase 1 entry point: fetch arXiv -> summarise -> print.

Run it with:  python scripts/run_digest.py

This is the first end-to-end slice of the pipeline: one source flows all the way
through the LLM to a printed digest. No ranking, dedup, or async yet.
"""

import sys
from datetime import date, datetime
from pathlib import Path

# src-layout shim (same as scripts/hello.py): put src/ on the import path so we
# can `import digest`. Goes away once we switch to an editable install.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from digest.collectors import collect_all  # noqa: E402 (after path setup)
from digest.curate import (  # noqa: E402
    curate, remember_kept, select_vectors, maybe_recaps,
)
from digest.ranking import rank_items  # noqa: E402
from digest.significance import enrich_significance  # noqa: E402
from digest.tagging import tag_items  # noqa: E402
from digest.assemble import (  # noqa: E402
    write_intro, render_digest, write_digest_file, save_digest_data,
)
from digest.memory_store import get_store  # noqa: E402
from digest.summarise import summarise_items  # noqa: E402
from digest.delivery import deliver_email  # noqa: E402
from digest import config  # noqa: E402


def main() -> None:
    # Windows consoles default to cp1252 and choke on Unicode; force UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from digest.observability import setup_logging, preflight, configure_tracing
    setup_logging()
    preflight()
    configure_tracing()

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
    delivered_vecs = select_vectors(result, items)   # vectors for the delivered subset
    print(f"{len(curated)} curated -> {len(items)} delivered "
          f"(<={config.TOP_N}, capped by source-type + score floor {config.SCORE_FLOOR}). "
          f"Checking OpenReview for papers...")
    enrich_significance(items)

    print("Tagging items for cross-reference...")
    tag_items(items)

    print("Summarising with Claude...\n")
    summaries = summarise_items(items)

    run_dt = datetime.now()
    # Quiet-day recaps: on a thin day, resurface a few past-delivered items.
    revisit = maybe_recaps(store, len(items), date.today())
    print("Writing the day's intro...\n")
    intro = write_intro(items)
    markdown = render_digest(items, summaries, run_dt, intro, revisit=revisit)
    print(markdown)

    try:
        path = write_digest_file(markdown, run_dt)
        print(f"wrote {path}")
        # Sidecar: the render inputs, so `scripts/deep_dive.py` can deepen an item
        # later without re-running the pipeline. Best-effort — never lose the run.
        stats = {"raw": raw_count, "curated": len(curated),
                 "delivered": len(items), "floor": config.SCORE_FLOOR}
        save_digest_data(path.with_suffix(".json"), items, summaries, intro, run_dt, stats=stats)
    except Exception as exc:  # noqa: BLE001 — digest already printed; don't lose the run
        print(f"[run] could not write digest file ({exc}); printed above only.",
              file=sys.stderr)

    # Deliver (Phase 9A): email the digest. Soft-fails; the file is already saved above.
    deliver_email(markdown, run_dt.date())

    # Delivered-only (Phase 6): remember what the reader saw, not the whole pool.
    remember_kept(items, delivered_vecs, store=store, run_date=date.today())


if __name__ == "__main__":
    main()
