"""
Task selector.

Given a mixed pool of scored candidates from the three miners, choose
the final N respecting:

- source caps (min history, max excision, max net-new)
- module diversity (>= K distinct modules across the chosen set)
- near-duplicate dedup by ``files_touched`` Jaccard similarity

Greedy selection prioritised by score, with two-phase filling:

1. Grab enough history candidates to meet ``min_history``.
2. Fill the remainder score-first while respecting source caps.
   Prefer candidates that grow the distinct-module set until the
   diversity floor is met; then relax.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SelectableCandidate:
    id: str
    source: str
    score: float
    module: str = ""
    files_touched: set[str] = field(default_factory=set)
    payload: Any = None


def select(
    candidates: list[SelectableCandidate],
    *,
    total: int = 10,
    min_history: int = 4,
    max_excision: int = 4,
    max_net_new: int = 3,
    min_distinct_modules: int = 4,
    dedup_similarity: float = 0.7,
) -> list[SelectableCandidate]:
    ordered = sorted(candidates, key=lambda c: c.score, reverse=True)
    deduped = _dedupe(ordered, dedup_similarity)

    by_source: dict[str, list[SelectableCandidate]] = defaultdict(list)
    for c in deduped:
        by_source[c.source].append(c)

    caps = {
        "history": total,
        "excision": max_excision,
        "net_new": max_net_new,
    }
    counts = {"history": 0, "excision": 0, "net_new": 0}
    chosen: list[SelectableCandidate] = []

    _fill_history_diverse_first(
        by_source["history"], chosen, counts, min_history
    )

    remaining = [c for c in deduped if c not in chosen]

    while len(chosen) < total and remaining:
        picked = _pick_diversity_first(
            remaining,
            chosen,
            counts,
            caps,
            min_distinct_modules,
        )
        if picked is None:
            picked = _pick_score_first(remaining, counts, caps)
        if picked is None:
            break
        chosen.append(picked)
        counts[picked.source] += 1
        remaining.remove(picked)

    return chosen


def _fill_history_diverse_first(
    history_pool: list[SelectableCandidate],
    chosen: list[SelectableCandidate],
    counts: dict[str, int],
    min_history: int,
) -> None:
    """Fill history slots preferring new modules when the pool allows.

    Iterates the score-sorted history pool twice: first taking one per
    module until we hit min_history, then relaxing to accept
    same-module candidates for any remaining slots.
    """
    seen_modules: set[str] = set()
    for c in history_pool:
        if counts["history"] >= min_history:
            return
        if c.module in seen_modules:
            continue
        chosen.append(c)
        counts["history"] += 1
        if c.module:
            seen_modules.add(c.module)

    for c in history_pool:
        if counts["history"] >= min_history:
            return
        if c in chosen:
            continue
        chosen.append(c)
        counts["history"] += 1


def _dedupe(
    candidates: list[SelectableCandidate], similarity: float
) -> list[SelectableCandidate]:
    kept: list[SelectableCandidate] = []
    for c in candidates:
        if any(
            _jaccard(c.files_touched, k.files_touched) >= similarity
            for k in kept
        ):
            continue
        kept.append(c)
    return kept


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _pick_diversity_first(
    remaining: list[SelectableCandidate],
    chosen: list[SelectableCandidate],
    counts: dict[str, int],
    caps: dict[str, int],
    min_distinct_modules: int,
) -> SelectableCandidate | None:
    distinct = {c.module for c in chosen if c.module}
    if len(distinct) >= min_distinct_modules:
        return None
    for c in remaining:
        if counts[c.source] >= caps[c.source]:
            continue
        if not c.module or c.module in distinct:
            continue
        return c
    return None


def _pick_score_first(
    remaining: list[SelectableCandidate],
    counts: dict[str, int],
    caps: dict[str, int],
) -> SelectableCandidate | None:
    for c in remaining:
        if counts[c.source] < caps[c.source]:
            return c
    return None
