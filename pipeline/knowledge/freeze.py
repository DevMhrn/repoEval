"""
Freeze the enriched graph to disk.

Writes:
    output/repo_graph.json         entire graph
    output/.okf/<module>.json      per-module facts extracted from the graph

Why split? Pipeline 3 often needs to iterate per-module without loading the
whole graph. Per-module files also make git diffs after re-running the
pipeline much smaller.

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path


def freeze(graph: dict, workspace: Path) -> dict:
    raise NotImplementedError("Phase 2")
