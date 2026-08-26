"""
Frozen graph schema.

Pydantic models that every consumer of the knowledge layer types
against. The on-disk form (``output/repo_graph.json``) is
``RepoGraph.model_dump_json``; loading is
``RepoGraph.model_validate_json``. That roundtrip must be lossless —
any consumer that reads the freshly-loaded model should be
indistinguishable from a consumer that constructed the same model
in-process.

Schema evolution: bump :data:`SCHEMA_VERSION` when a field is removed
or its meaning changes. New optional fields are backward-compatible
and don't need a bump.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: str = "1.0.0"


NodeType = Literal["module", "class", "function", "method"]
EdgeType = Literal["imports", "calls", "defines", "inherits"]


class Node(BaseModel):
    """A node in the repo graph.

    ``id`` is a stable dotted path (e.g. ``glom.core.glom`` or
    ``glom.core.Spec.match``). Downstream code uses it as the key
    everywhere — mining, task manifests, evidence reports — so keep it
    unique and reader-friendly.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    file: str
    line: int = 0
    end_line: int = 0
    docstring: str | None = None
    signature: str | None = None
    is_public: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    """A directed relationship between two nodes."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepoGraph(BaseModel):
    """The full knowledge layer artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    repo: str
    commit: str = ""
    generated_at: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def find_node(self, node_id: str) -> Node | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def edges_from(self, source_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == source_id]

    def edges_to(self, target_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == target_id]
