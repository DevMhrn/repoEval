"""Tests for pipeline.knowledge.build_graph."""

from __future__ import annotations

from pathlib import Path

from pipeline.knowledge.build_graph import build_graph
from pipeline.knowledge.schema import RepoGraph


def _seed_small_pkg(root: Path) -> None:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text(
        '"""Core module."""\n'
        "def target():\n"
        "    return 42\n"
        "class Spec:\n"
        "    def match(self, x):\n"
        "        return target()\n"
    )
    (pkg / "mutation.py").write_text(
        "from pkg.core import target\n"
        "def assign():\n"
        "    return target()\n"
    )


def test_build_produces_expected_nodes(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, _ = build_graph(tmp_path, repo_name="test-repo", commit="abc123")

    ids = graph.node_ids()
    assert "pkg" in ids
    assert "pkg.core" in ids
    assert "pkg.core.target" in ids
    assert "pkg.core.Spec" in ids
    assert "pkg.core.Spec.match" in ids
    assert "pkg.mutation" in ids
    assert "pkg.mutation.assign" in ids


def test_build_produces_import_edges(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, _ = build_graph(tmp_path)
    import_pairs = {
        (e.source, e.target)
        for e in graph.edges
        if e.type == "imports"
    }
    assert ("pkg.mutation", "pkg.core") in import_pairs


def test_build_produces_call_edges(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, _ = build_graph(tmp_path)
    call_pairs = {
        (e.source, e.target)
        for e in graph.edges
        if e.type == "calls"
    }
    assert ("pkg.mutation.assign", "pkg.core.target") in call_pairs


def test_networkx_view_has_matching_nodes_and_edges(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, nx_graph = build_graph(tmp_path)
    assert set(nx_graph.nodes) == graph.node_ids()
    for edge in graph.edges:
        assert nx_graph.has_edge(edge.source, edge.target)


def test_repo_graph_roundtrips_through_json(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, _ = build_graph(tmp_path, repo_name="r", commit="c1", generated_at="2026-01-01T00:00:00+00:00")
    data = graph.model_dump_json()
    reloaded = RepoGraph.model_validate_json(data)
    assert reloaded == graph


def test_build_is_deterministic_with_fixed_generated_at(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    a, _ = build_graph(tmp_path, generated_at="2026-01-01T00:00:00")
    b, _ = build_graph(tmp_path, generated_at="2026-01-01T00:00:00")
    assert a == b


def test_empty_directory_produces_empty_graph(tmp_path: Path):
    graph, nx_graph = build_graph(tmp_path)
    assert graph.nodes == []
    assert graph.edges == []
    assert len(nx_graph.nodes) == 0


def test_skip_tests_excludes_test_modules(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_core.py").write_text(
        "def test_thing(): pass\n"
    )
    graph, _ = build_graph(tmp_path, skip_tests=True)
    ids = graph.node_ids()
    assert "pkg.core" in ids
    assert "tests.test_core" not in ids


def test_nodes_sorted_by_id(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, _ = build_graph(tmp_path)
    ids = [n.id for n in graph.nodes]
    assert ids == sorted(ids)


def test_to_networkx_carries_node_attributes(tmp_path: Path):
    _seed_small_pkg(tmp_path)
    graph, nx_graph = build_graph(tmp_path)
    fn_data = nx_graph.nodes["pkg.core.target"]
    assert fn_data["type"] == "function"
    assert fn_data["file"] == "pkg/core.py"
