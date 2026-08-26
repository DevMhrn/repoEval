"""Tests for pipeline.knowledge.enrich_coverage."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.knowledge.enrich_coverage import enrich_with_coverage
from pipeline.knowledge.schema import Node, RepoGraph


def _graph(nodes: list[Node]) -> RepoGraph:
    return RepoGraph(
        repo="x",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
    )


def _report(tmp_path: Path, *, rates: dict[str, float], threshold: float = 0.6) -> Path:
    path = tmp_path / "coverage_report.json"
    path.write_text(
        json.dumps(
            {
                "commit": "",
                "threshold": threshold,
                "overall": 0.5,
                "line_rate_by_file": rates,
                "gaps": [],
            }
        )
    )
    return path


def test_attaches_coverage_metadata_to_matching_files(tmp_path: Path):
    graph = _graph(
        [
            Node(id="pkg.core", type="module", file="pkg/core.py"),
            Node(id="pkg.util", type="module", file="pkg/util.py"),
        ]
    )
    report = _report(tmp_path, rates={"pkg/core.py": 0.9, "pkg/util.py": 0.4})

    enriched = enrich_with_coverage(graph, report)
    core = enriched.find_node("pkg.core")
    util = enriched.find_node("pkg.util")

    assert core.metadata["coverage"]["line_rate"] == 0.9
    assert core.metadata["coverage"]["is_gap"] is False
    assert util.metadata["coverage"]["line_rate"] == 0.4
    assert util.metadata["coverage"]["is_gap"] is True


def test_uses_report_threshold_for_gap_flag(tmp_path: Path):
    graph = _graph([Node(id="pkg.core", type="module", file="pkg/core.py")])
    report = _report(tmp_path, rates={"pkg/core.py": 0.55}, threshold=0.5)

    enriched = enrich_with_coverage(graph, report)
    assert enriched.find_node("pkg.core").metadata["coverage"]["is_gap"] is False


def test_nodes_not_in_report_get_no_metadata(tmp_path: Path):
    graph = _graph(
        [
            Node(id="pkg.core", type="module", file="pkg/core.py"),
            Node(id="pkg.ghost", type="module", file="pkg/ghost.py"),
        ]
    )
    report = _report(tmp_path, rates={"pkg/core.py": 0.9})

    enriched = enrich_with_coverage(graph, report)
    assert "coverage" in enriched.find_node("pkg.core").metadata
    assert "coverage" not in enriched.find_node("pkg.ghost").metadata


def test_missing_report_returns_graph_unchanged(tmp_path: Path):
    graph = _graph([Node(id="pkg.core", type="module", file="pkg/core.py")])
    enriched = enrich_with_coverage(graph, tmp_path / "nope.json")
    assert enriched == graph


def test_malformed_report_returns_graph_unchanged(tmp_path: Path):
    path = tmp_path / "coverage_report.json"
    path.write_text("not json{")
    graph = _graph([Node(id="pkg.core", type="module", file="pkg/core.py")])
    enriched = enrich_with_coverage(graph, path)
    assert enriched == graph


def test_preserves_original_graph(tmp_path: Path):
    graph = _graph([Node(id="pkg.core", type="module", file="pkg/core.py")])
    report = _report(tmp_path, rates={"pkg/core.py": 0.9})

    enriched = enrich_with_coverage(graph, report)
    assert "coverage" in enriched.find_node("pkg.core").metadata
    assert graph.find_node("pkg.core").metadata == {}


def test_multiple_nodes_from_same_file_all_annotated(tmp_path: Path):
    graph = _graph(
        [
            Node(id="pkg.core", type="module", file="pkg/core.py"),
            Node(id="pkg.core.a", type="function", file="pkg/core.py"),
            Node(id="pkg.core.b", type="function", file="pkg/core.py"),
        ]
    )
    report = _report(tmp_path, rates={"pkg/core.py": 0.75})
    enriched = enrich_with_coverage(graph, report)
    for node_id in ("pkg.core", "pkg.core.a", "pkg.core.b"):
        assert enriched.find_node(node_id).metadata["coverage"]["line_rate"] == 0.75
