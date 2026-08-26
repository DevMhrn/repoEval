"""End-to-end tests for pipeline.knowledge.stage."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from pipeline.common.stage import StageContext
from pipeline.knowledge.schema import RepoGraph
from pipeline.knowledge.stage import KnowledgeStage


def _git(cwd: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        env=env,
    )


def _seed_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text(
        '"""Core module."""\n'
        "def target():\n"
        "    return 42\n"
    )
    (pkg / "mutation.py").write_text(
        "from pkg.core import target\n"
        "def assign():\n"
        "    return target()\n"
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname='t'\nversion='0.0.0'\n"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")


def _ctx(repo: Path, workspace: Path) -> StageContext:
    return StageContext(
        repo_path=repo,
        workspace=workspace,
        config={"knowledge": {"include_test_files": False}, "llm": {"mode": "replay"}},
        run_id="knowledge-x",
        extra={"generated_at": "2026-01-01T00:00:00+00:00"},
    )


def test_stage_writes_graph_and_okf(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo(repo)

    stage = KnowledgeStage()
    result = stage.execute(_ctx(repo, workspace))
    assert result.success

    graph_path = workspace / "repo_graph.json"
    okf_dir = workspace / ".okf"
    assert graph_path.exists()
    assert okf_dir.exists()
    okf_files = sorted(okf_dir.glob("*.json"))
    assert okf_files


def test_stage_graph_is_schema_valid(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo(repo)

    KnowledgeStage().execute(_ctx(repo, workspace))
    graph_path = workspace / "repo_graph.json"
    graph = RepoGraph.model_validate_json(graph_path.read_text())
    assert graph.node_ids() >= {"pkg", "pkg.core", "pkg.core.target"}


def test_stage_second_run_is_cache_hit(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo(repo)

    stage = KnowledgeStage()
    ctx = _ctx(repo, workspace)
    first = stage.execute(ctx)
    second = stage.execute(ctx)
    assert first.success and second.success
    assert second.cache_hit is True


def test_stage_verify_false_before_run(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_repo(repo)
    stage = KnowledgeStage()
    assert stage.verify(_ctx(repo, workspace)) is False


def test_okf_files_contain_expected_shape(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo(repo)
    KnowledgeStage().execute(_ctx(repo, workspace))

    core_okf = workspace / ".okf" / "pkg.core.json"
    assert core_okf.exists()
    data = json.loads(core_okf.read_text())
    assert data["module"] == "pkg.core"
    assert "target" in data["functions"]


def test_stage_survives_without_llm_fixtures(tmp_path: Path):
    """No fixtures in replay mode → llm enrichment skipped, graph still written."""
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo(repo)

    ctx = StageContext(
        repo_path=repo,
        workspace=workspace,
        config={"knowledge": {}, "llm": {"mode": "replay", "fixtures_dir": "does/not/exist"}},
        run_id="x",
        extra={"generated_at": "2026-01-01T00:00:00+00:00"},
    )
    result = KnowledgeStage().execute(ctx)
    assert result.success
    assert (workspace / "repo_graph.json").exists()
