"""
Git enrichment.

For each graph node backed by a file (functions, classes), attach:
    - last_commit: sha, date, author, message
    - touch_count: number of commits touching the file in the last N months
    - bugfix_signals: commits whose messages match fix/bug/regression patterns

This is what the history miner in Pipeline 3 uses to identify good tasks.

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path


def enrich_with_git(graph: dict, repo_path: Path) -> dict:
    raise NotImplementedError("Phase 2")
