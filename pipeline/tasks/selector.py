"""
Selector — scoring, deduplication, and diversity enforcement.

Given a pool of candidates from multiple miners, choose the final N such that:
    - Source-type caps are respected.
    - At least min_distinct_modules distinct modules are represented.
    - No two candidates cover the same underlying change (dedupe by diff hash
      and by affected function set).

Selection uses a simple weighted score:
    difficulty * novelty * (1 / near_duplicates)

Phase 0 status: STUB.
"""

from __future__ import annotations


def select(candidates: list[dict], config: dict) -> list[dict]:
    raise NotImplementedError("Phase 3")
