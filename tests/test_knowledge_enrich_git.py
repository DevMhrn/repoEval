"""Tests for pipeline.knowledge.enrich_git."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pipeline.knowledge.enrich_git import enrich_with_git
from pipeline.knowledge.schema import Node, RepoGraph


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout


def _seed_repo_with_history(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    (root / "a.py").write_text("def one():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first: add a.py")

    (root / "b.py").write_text("def two():\n    return 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "second: add b.py")

    (root / "a.py").write_text(
        "def one():\n"
        "    return 1\n"
        "def one_and_a_half():\n"
        "    return 1.5\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "third: extend a.py")


def _graph_from(root: Path, nodes: list[Node]) -> RepoGraph:
    return RepoGraph(
        repo=str(root),
        commit="",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
    )


def test_enrich_attaches_last_commit_per_file(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    graph = _graph_from(
        tmp_path,
        [
            Node(id="a", type="module", file="a.py"),
            Node(id="b", type="module", file="b.py"),
        ],
    )
    enriched = enrich_with_git(graph, tmp_path)

    a_node = enriched.find_node("a")
    b_node = enriched.find_node("b")
    assert "git" in a_node.metadata
    assert "git" in b_node.metadata
    assert a_node.metadata["git"]["last_message"].startswith("third:")
    assert b_node.metadata["git"]["last_message"].startswith("second:")


def test_enrich_preserves_original_graph(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    node = Node(id="a", type="module", file="a.py")
    graph = _graph_from(tmp_path, [node])

    enriched = enrich_with_git(graph, tmp_path)
    assert "git" in enriched.find_node("a").metadata
    assert graph.find_node("a").metadata == {}


def test_enrich_skips_external_files(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    graph = _graph_from(
        tmp_path,
        [
            Node(id="ext", type="module", file="<external>/os"),
            Node(id="a", type="module", file="a.py"),
        ],
    )
    enriched = enrich_with_git(graph, tmp_path)
    assert enriched.find_node("ext").metadata == {}
    assert "git" in enriched.find_node("a").metadata


def test_enrich_gracefully_handles_untracked_file(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    graph = _graph_from(
        tmp_path,
        [Node(id="ghost", type="module", file="never_existed.py")],
    )
    enriched = enrich_with_git(graph, tmp_path)
    # No git metadata because file isn't tracked.
    assert enriched.find_node("ghost").metadata == {}


def test_enrich_gracefully_handles_non_git_workspace(tmp_path: Path):
    (tmp_path / "a.py").write_text("pass")
    graph = _graph_from(
        tmp_path, [Node(id="a", type="module", file="a.py")]
    )
    enriched = enrich_with_git(graph, tmp_path)
    assert enriched.find_node("a").metadata == {}


def test_per_function_history_when_enabled(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    fn_node = Node(
        id="a.one_and_a_half",
        type="function",
        file="a.py",
        line=3,
        end_line=4,
    )
    graph = _graph_from(tmp_path, [fn_node])
    enriched = enrich_with_git(graph, tmp_path, per_function_history=True)

    meta = enriched.find_node("a.one_and_a_half").metadata.get("git", {})
    shas = meta.get("commits_touching_span", [])
    assert isinstance(shas, list)
    # At least the third: commit should be in the span history.
    assert len(shas) >= 1


def test_per_function_history_disabled_by_default(tmp_path: Path):
    _seed_repo_with_history(tmp_path)
    fn_node = Node(
        id="a.one",
        type="function",
        file="a.py",
        line=1,
        end_line=2,
    )
    graph = _graph_from(tmp_path, [fn_node])
    enriched = enrich_with_git(graph, tmp_path)
    meta = enriched.find_node("a.one").metadata.get("git", {})
    assert "commits_touching_span" not in meta
