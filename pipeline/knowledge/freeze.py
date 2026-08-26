"""
Freeze the enriched graph to disk.

Writes ``output/repo_graph.json`` in a form that round-trips through
:meth:`RepoGraph.model_validate_json`. Sorted keys keep the diff
small across re-runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import RepoGraph


def freeze_repo_graph(graph: RepoGraph, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Round-trip through json.dumps to control sort_keys.
    data = json.loads(graph.model_dump_json())
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    return path
