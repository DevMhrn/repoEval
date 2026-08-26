"""Tests for pipeline.knowledge.schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.knowledge.schema import (
    SCHEMA_VERSION,
    Edge,
    Node,
    RepoGraph,
)


def _node(id_: str = "pkg.mod.fn", **overrides) -> Node:
    data = {"id": id_, "type": "function", "file": "pkg/mod.py"}
    data.update(overrides)
    return Node(**data)


def _edge(**overrides) -> Edge:
    data = {"source": "a", "target": "b", "type": "calls"}
    data.update(overrides)
    return Edge(**data)


def _graph(**overrides) -> RepoGraph:
    data = {"repo": "https://x/y", "generated_at": "2026-01-01T00:00:00+00:00"}
    data.update(overrides)
    return RepoGraph(**data)


def test_node_roundtrip():
    n = _node(id_="pkg.mod.fn", line=10, end_line=20, docstring="d", signature="(x)")
    data = n.model_dump_json()
    n2 = Node.model_validate_json(data)
    assert n == n2


def test_edge_roundtrip():
    e = _edge(source="a", target="b", type="calls", weight=2.0)
    e2 = Edge.model_validate_json(e.model_dump_json())
    assert e == e2


def test_graph_roundtrip_with_nodes_and_edges():
    g = _graph(
        repo="r",
        commit="sha1",
        nodes=[_node(), _node(id_="pkg.other")],
        edges=[_edge()],
    )
    reloaded = RepoGraph.model_validate_json(g.model_dump_json())
    assert reloaded == g
    assert reloaded.schema_version == SCHEMA_VERSION


def test_node_type_validated():
    with pytest.raises(ValidationError):
        _node(type="package")


def test_edge_type_validated():
    with pytest.raises(ValidationError):
        _edge(type="depends_on")


def test_node_requires_id():
    with pytest.raises(ValidationError):
        Node(type="function", file="x.py")


def test_extra_fields_forbidden_on_node():
    with pytest.raises(ValidationError):
        Node(id="x", type="function", file="x.py", surprise=1)


def test_extra_fields_forbidden_on_graph():
    with pytest.raises(ValidationError):
        RepoGraph(
            repo="r",
            generated_at="2026-01-01T00:00:00",
            surprise="uh-oh",
        )


def test_find_node_returns_match():
    g = _graph(nodes=[_node(id_="a"), _node(id_="b"), _node(id_="c")])
    assert g.find_node("b").id == "b"
    assert g.find_node("nope") is None


def test_node_ids_returns_set():
    g = _graph(nodes=[_node(id_="a"), _node(id_="b")])
    assert g.node_ids() == {"a", "b"}


def test_edges_from_and_to():
    e1 = _edge(source="a", target="b", type="calls")
    e2 = _edge(source="a", target="c", type="imports")
    e3 = _edge(source="d", target="a", type="inherits")
    g = _graph(edges=[e1, e2, e3])
    assert g.edges_from("a") == [e1, e2]
    assert g.edges_to("a") == [e3]


def test_defaults_populate_reasonable_values():
    n = _node()
    assert n.line == 0
    assert n.end_line == 0
    assert n.docstring is None
    assert n.is_public is True
    assert n.metadata == {}


def test_schema_version_present_by_default():
    g = _graph()
    assert g.schema_version == SCHEMA_VERSION
