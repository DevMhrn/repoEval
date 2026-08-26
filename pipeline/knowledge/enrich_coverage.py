"""
Coverage import.

Reads a coverage report emitted by :mod:`pipeline.hygiene.coverage`
and attaches ``coverage`` metadata to each graph node whose ``file``
matches an entry. Nodes for files that weren't covered (or aren't in
the report at all) are left untouched.

The gap flag is precomputed here so downstream consumers don't need
to know the threshold used at hygiene time.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import Node, RepoGraph


def enrich_with_coverage(
    graph: RepoGraph,
    coverage_report_path: Path,
) -> RepoGraph:
    if not coverage_report_path.exists():
        return graph

    try:
        data = json.loads(coverage_report_path.read_text())
    except (json.JSONDecodeError, OSError):
        return graph

    rate_by_file: dict[str, float] = data.get("line_rate_by_file", {})
    threshold: float = data.get("threshold", 0.6)

    enriched: list[Node] = []
    for node in graph.nodes:
        node_copy = node.model_copy(deep=True)
        rate = rate_by_file.get(node.file)
        if rate is not None:
            node_copy.metadata["coverage"] = {
                "line_rate": rate,
                "is_gap": rate < threshold,
                "threshold": threshold,
            }
        enriched.append(node_copy)

    return graph.model_copy(update={"nodes": enriched})
