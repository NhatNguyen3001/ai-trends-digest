"""Within-day de-duplication.

Two passes over a single day's items:
  1. exact   — same canonical URL or same (source,id) -> drop, keep the first.
  2. semantic (later tasks) — same *story* in different words -> merge.

A merged item records the duplicates it absorbed in ``Item.merged_sources`` so
the digest can show "also covered by ...". All external calls (Voyage, Claude)
are injected so the logic tests without network access.
"""

import json
import sys
from urllib.parse import urlsplit

import numpy as np

from digest import config
from digest.embeddings import embed_texts
from digest.llm import get_client
from digest.models import Item


def _normalize_url(url: str) -> str:
    """Canonical form for comparing links: no scheme, no www, no trailing slash,
    no query/fragment, lowercased host+path."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}".lower()


def _exact_dedup(items: list[Item]) -> list[Item]:
    """Keep the first item per normalized URL and per (source, id); later exact
    duplicates are absorbed into the survivor's ``merged_sources``."""
    seen: dict[str, Item] = {}
    order: list[Item] = []
    for it in items:
        keys = [f"url:{_normalize_url(it.url)}", f"id:{it.source}:{it.id}"]
        hit = next((seen[k] for k in keys if k in seen), None)
        if hit is None:
            for k in keys:
                seen[k] = it
            order.append(it)
        else:
            hit.merged_sources.append(f"{it.source}: {it.url}")
    return order


def _cosine_matrix(vectors: list[list[float]]) -> np.ndarray:
    """Symmetric NxN matrix of cosine similarities between row vectors."""
    mat = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0                    # avoid divide-by-zero
    unit = mat / norms
    return unit @ unit.T


def _semantic_clusters(n, sim, sim_high, sim_low, gray_check):
    """Single-link clustering of indices 0..n-1 by similarity.

    A pair joins when sim >= sim_high, or it's in [sim_low, sim_high) and
    ``gray_check`` confirms it. Returns clusters as sorted index lists.
    """
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    gray_pairs: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            s = sim[i][j]
            if s >= sim_high:
                union(i, j)
            elif s >= sim_low:
                gray_pairs.append((i, j))

    for i, j in gray_check(gray_pairs) if gray_pairs else set():
        union(i, j)

    groups: dict[int, list[int]] = {}
    for x in range(n):
        groups.setdefault(find(x), []).append(x)
    return [sorted(g) for g in groups.values()]


def check_same_story(items, pairs, *, client_factory=get_client):
    """Ask Claude which gray-band pairs describe the same story.

    pairs is a list of (i, j) index pairs. Returns the subset judged "same".
    Output is keyed by the pair's position (index-keyed, never positional array)
    so a dropped answer can't shift the rest. Soft-fail -> empty set (distinct).
    """
    if not pairs:
        return set()

    lines = []
    for k, (i, j) in enumerate(pairs):
        lines.append(
            f"[{k}] A: {items[i].title} — {items[i].summary[:200]}\n"
            f"     B: {items[j].title} — {items[j].summary[:200]}"
        )
    instruction = (
        "For each numbered pair below, are A and B about the SAME underlying "
        "story/announcement/paper (not merely the same topic)? Return ONLY a JSON "
        'object mapping each pair index (string key) to "yes" or "no" — e.g. '
        f'{{"0": "yes", "1": "no"}}. Include indices 0 to {len(pairs) - 1}. '
        "No prose, no markdown.\n\n" + "\n\n".join(lines)
    )

    try:
        client = client_factory()
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": instruction}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        verdicts = json.loads(text)
    except Exception as exc:  # noqa: BLE001 — soft-fail by design
        print(f"[dedup] same-story check failed ({exc}); treating pairs as distinct.",
              file=sys.stderr)
        return set()

    same = set()
    for k, pair in enumerate(pairs):
        if str(verdicts.get(str(k), "no")).strip().lower().startswith("y"):
            same.add(pair)
    return same


def _merge_cluster(group: list[Item]) -> Item:
    """Collapse a cluster to one canonical item (richest summary wins); the rest
    are recorded in the survivor's merged_sources."""
    canonical = max(group, key=lambda it: len(it.summary or ""))
    for other in group:
        if other is canonical:
            continue
        canonical.merged_sources.append(f"{other.source}: {other.url}")
        canonical.merged_sources.extend(other.merged_sources)
    return canonical


def dedup_within_day(items, *, embed_fn=embed_texts, same_story_fn=check_same_story):
    """Exact then semantic de-duplication of one day's items."""
    items = _exact_dedup(items)
    if len(items) < 2:
        return items

    texts = [f"{it.title} {it.summary}".strip() for it in items]
    vectors = embed_fn(texts)
    if vectors is None:                        # embeddings unavailable -> exact only
        return items

    sim = _cosine_matrix(vectors)
    clusters = _semantic_clusters(
        len(items), sim, config.SIM_HIGH, config.SIM_LOW,
        gray_check=lambda pairs: same_story_fn(items, pairs),
    )
    # Preserve original order by the smallest index in each cluster.
    clusters.sort(key=min)
    return [_merge_cluster([items[i] for i in group]) for group in clusters]
