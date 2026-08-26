"""
Assemble a full :class:`RepoGraph` and a transient NetworkX view.

Walks every Python module under ``repo_path``, runs node and edge
extractors, resolves cross-references, and returns:

- :class:`RepoGraph` — the persistable Pydantic form. Written to disk
  in Phase 2.12 and consumed by Pipeline 3.
- :class:`networkx.DiGraph` — a transient in-memory view for cheap
  graph queries (BFS, shortest path, subgraph). Not persisted;
  downstream code that needs it rebuilds from the RepoGraph via
  :func:`to_networkx`.

``generated_at`` is optional so callers can hold time still for
deterministic tests. In production, omit and we stamp with UTC now.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import networkx as nx

from ..common.ecosystem import EcosystemStrategy
from .extractors.calls import extract_call_edges
from .extractors.imports import extract_import_edges
from .extractors.nodes import extract_nodes
from .schema import RepoGraph
from .walkers.python import walk_python


def build_graph(
    repo_path: Path,
    strategy: EcosystemStrategy | None = None,
    *,
    repo_name: str = "",
    commit: str = "",
    generated_at: str | None = None,
    skip_tests: bool = False,
) -> tuple[RepoGraph, nx.DiGraph]:
    _ = strategy  # reserved for polyglot dispatch

    parsed = list(walk_python(repo_path, skip_tests=skip_tests))

    all_nodes = []
    for module in parsed:
        all_nodes.extend(extract_nodes(module, repo_root=repo_path))

    known_module_ids = {m.module_id for m in parsed}
    known_node_ids = {n.id for n in all_nodes}

    all_edges = []
    for module in parsed:
        all_edges.extend(
            extract_import_edges(module, known_module_ids=known_module_ids)
        )
        all_edges.extend(
            extract_call_edges(module, known_node_ids=known_node_ids)
        )

    graph = RepoGraph(
        repo=repo_name or str(repo_path),
        commit=commit,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        nodes=sorted(all_nodes, key=lambda n: n.id),
        edges=sorted(all_edges, key=lambda e: (e.source, e.target, e.type)),
    )

    return graph, to_networkx(graph)


def to_networkx(graph: RepoGraph) -> nx.DiGraph:
    g = nx.DiGraph()
    for node in graph.nodes:
        g.add_node(node.id, **node.model_dump(exclude={"id"}))
    for edge in graph.edges:
        g.add_edge(
            edge.source,
            edge.target,
            **edge.model_dump(exclude={"source", "target"}),
        )
    return g
