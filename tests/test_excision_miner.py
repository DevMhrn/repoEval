"""Tests for pipeline.tasks.miners.excision."""

from __future__ import annotations

from pathlib import Path

from pipeline.knowledge.schema import Edge, Node, RepoGraph
from pipeline.tasks.miners.excision import (
    ExcisionCandidate,
    _algorithmic_score,
    _score,
    mine_excision,
)


def _fn(id_: str, file: str, line: int, end_line: int, *, line_rate: float = 1.0):
    node = Node(
        id=id_,
        type="function",
        file=file,
        line=line,
        end_line=end_line,
        signature="(x)",
        is_public=True,
    )
    node.metadata["coverage"] = {"line_rate": line_rate}
    return node


def _graph_with(nodes, edges=None):
    return RepoGraph(
        repo="x",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
        edges=edges or [],
    )


def _seed_source(tmp_path: Path, file: str, source: str) -> Path:
    path = tmp_path / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return tmp_path


def test_mine_returns_covered_function(tmp_path: Path):
    src = (
        "def wide(a):\n"
        + "    x = 1\n" * 15
        + "    return x\n"
    )
    _seed_source(tmp_path, "pkg/core.py", src)
    graph = _graph_with(
        [
            _fn("pkg.core.wide", "pkg/core.py", 1, 18, line_rate=0.95),
        ],
        edges=[
            Edge(source="tests.test_core.test_a", target="pkg.core.wide", type="calls"),
        ],
    )
    candidates = mine_excision(graph, tmp_path)
    assert len(candidates) == 1
    assert candidates[0].node_id == "pkg.core.wide"


def test_mine_excludes_low_coverage(tmp_path: Path):
    src = "def small(a):\n" + "    x = 1\n" * 15 + "    return x\n"
    _seed_source(tmp_path, "pkg/core.py", src)
    graph = _graph_with(
        [_fn("pkg.core.small", "pkg/core.py", 1, 18, line_rate=0.5)],
        edges=[
            Edge(source="tests.test_core.test_a", target="pkg.core.small", type="calls"),
        ],
    )
    assert mine_excision(graph, tmp_path) == []


def test_mine_excludes_tiny_functions(tmp_path: Path):
    _seed_source(tmp_path, "x.py", "def f():\n    return 1\n")
    graph = _graph_with(
        [_fn("x.f", "x.py", 1, 2, line_rate=1.0)],
        edges=[Edge(source="tests.test_x.test", target="x.f", type="calls")],
    )
    assert mine_excision(graph, tmp_path) == []


def test_mine_excludes_huge_functions(tmp_path: Path):
    _seed_source(tmp_path, "x.py", "\n" * 200)
    graph = _graph_with(
        [_fn("x.big", "x.py", 1, 190, line_rate=1.0)],
        edges=[Edge(source="tests.test_x.test", target="x.big", type="calls")],
    )
    assert mine_excision(graph, tmp_path) == []


def test_mine_excludes_private_functions(tmp_path: Path):
    src = "def _priv():\n" + "    return 1\n" * 15
    _seed_source(tmp_path, "x.py", src)
    node = _fn("x._priv", "x.py", 1, 16, line_rate=1.0)
    node.is_public = False
    graph = _graph_with(
        [node],
        edges=[Edge(source="tests.test_x.test", target="x._priv", type="calls")],
    )
    assert mine_excision(graph, tmp_path) == []


def test_algorithmic_score_higher_for_loopy_code(tmp_path: Path):
    complex_src = (
        "def alg(xs):\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        if x > 0:\n"
        "            total = total + x\n"
        "        elif x == 0:\n"
        "            continue\n"
        "        else:\n"
        "            total = total - 1\n"
        "    return total\n"
    )
    _seed_source(tmp_path, "a.py", complex_src)
    complex_node = _fn("a.alg", "a.py", 1, 11)

    simple_src = "def s(x):\n" + "    y = x\n" * 12 + "    return y\n"
    (tmp_path / "b.py").write_text(simple_src)
    simple_node = _fn("b.s", "b.py", 1, 15)

    assert _algorithmic_score(tmp_path, complex_node) > _algorithmic_score(tmp_path, simple_node)


def test_scoring_orders_richer_candidates_higher():
    c1 = ExcisionCandidate(
        node_id="a", file="a.py", line=1, end_line=15, signature="()",
        docstring="", body_loc=15, line_rate=1.0, tests_ref_count=1,
        algorithmic_score=0.1,
    )
    c2 = ExcisionCandidate(
        node_id="b", file="b.py", line=1, end_line=30, signature="()",
        docstring="", body_loc=30, line_rate=1.0, tests_ref_count=3,
        algorithmic_score=0.5,
    )
    _score(c1)
    _score(c2)
    assert c2.score > c1.score


def test_ref_count_zero_excluded_when_min_is_one(tmp_path: Path):
    src = "def f():\n" + "    return 1\n" * 15
    _seed_source(tmp_path, "x.py", src)
    graph = _graph_with([_fn("x.f", "x.py", 1, 16, line_rate=1.0)])
    assert mine_excision(graph, tmp_path) == []


def test_no_coverage_metadata_falls_back_to_tests_ref(tmp_path: Path):
    src = "def wide(a):\n" + "    x = 1\n" * 15 + "    return x\n"
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "core.py").write_text(src)
    node = Node(
        id="pkg.core.wide",
        type="function",
        file="pkg/core.py",
        line=1,
        end_line=18,
        signature="(a)",
        is_public=True,
    )
    # Note: no coverage metadata at all.
    graph = _graph_with(
        [node],
        edges=[
            Edge(source=f"tests.test_core.test_{i}", target="pkg.core.wide", type="calls")
            for i in range(4)
        ],
    )
    result = mine_excision(graph, tmp_path)
    assert len(result) == 1
    assert result[0].tests_ref_count == 4


def test_no_coverage_and_few_test_refs_still_excluded(tmp_path: Path):
    src = "def wide(a):\n" + "    x = 1\n" * 15 + "    return x\n"
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "core.py").write_text(src)
    node = Node(
        id="pkg.core.wide",
        type="function",
        file="pkg/core.py",
        line=1,
        end_line=18,
        signature="(a)",
        is_public=True,
    )
    graph = _graph_with(
        [node],
        edges=[
            Edge(source="tests.test_core.only_one", target="pkg.core.wide", type="calls"),
        ],
    )
    # No coverage; only 1 test ref — below the fallback threshold of 3.
    assert mine_excision(graph, tmp_path) == []


def test_limit_caps_returned_candidates(tmp_path: Path):
    nodes = []
    edges = []
    for i in range(10):
        _seed_source(tmp_path, f"m{i}.py", "def f():\n" + "    return 1\n" * 15)
        nodes.append(_fn(f"m{i}.f", f"m{i}.py", 1, 16, line_rate=1.0))
        edges.append(Edge(source=f"tests.test_{i}.t", target=f"m{i}.f", type="calls"))
    graph = _graph_with(nodes, edges)
    assert len(mine_excision(graph, tmp_path, limit=3)) == 3
