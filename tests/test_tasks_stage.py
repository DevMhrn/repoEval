"""End-to-end-ish tests for pipeline.tasks.stage."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from pipeline.common.stage import StageContext
from pipeline.tasks.stage import TasksStage


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


def _seed_repo_with_bugfix(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text(
        "def parse(s):\n    return s.upper()\n"
    )
    (root / "pyproject.toml").write_text("[project]\nname='t'\nversion='0.0.0'\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    (pkg / "core.py").write_text(
        "def parse(s):\n    return s.strip().upper()\n"
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        "from pkg.core import parse\n"
        "def test_strip(): assert parse(' x') == 'X'\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix parse to strip whitespace")


def _seed_knowledge_layer(repo: Path, workspace: Path) -> None:
    """Run KnowledgeStage against the repo to produce repo_graph.json."""
    from pipeline.knowledge.stage import KnowledgeStage

    kn_ctx = StageContext(
        repo_path=repo,
        workspace=workspace,
        config={
            "knowledge": {"include_test_files": False},
            "llm": {"mode": "replay"},
        },
        run_id="knowledge-seed",
        extra={"generated_at": "2026-01-01T00:00:00+00:00"},
    )
    KnowledgeStage().execute(kn_ctx)


def _ctx(repo: Path, workspace: Path, **cfg_overrides) -> StageContext:
    cfg = {
        "tasks": {
            "total": 3,
            "min_history_derived": 1,
            "max_excision": 4,
            "max_net_new": 3,
            "min_distinct_modules": 1,
            "mine_limit": 10,
        },
        "llm": {"mode": "replay"},
    }
    cfg.update(cfg_overrides)
    return StageContext(
        repo_path=repo,
        workspace=workspace,
        config=cfg,
        run_id="tasks-x",
    )


def test_verify_false_before_run(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_repo_with_bugfix(repo)
    assert TasksStage().verify(_ctx(repo, workspace)) is False


def test_run_produces_tasks_and_index(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo_with_bugfix(repo)
    _seed_knowledge_layer(repo, workspace)

    result = TasksStage().execute(_ctx(repo, workspace))
    assert result.success is True

    tasks_json = workspace.parent / "tasks.json"
    assert tasks_json.exists()
    entries = json.loads(tasks_json.read_text())
    assert len(entries) >= 1


def test_run_writes_task_folders(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo_with_bugfix(repo)
    _seed_knowledge_layer(repo, workspace)

    TasksStage().execute(_ctx(repo, workspace))
    tasks_root = workspace.parent / "tasks"
    tasks = sorted(p.name for p in tasks_root.iterdir() if p.is_dir())
    assert tasks
    first = tasks_root / tasks[0]
    assert (first / "task.json").exists()
    assert (first / "instruction.md").exists()
    assert (first / "input").exists()
    assert (first / "solution").exists()
    assert (first / "verifier").exists()
    assert (first / "goldenSolution.md").exists()


def test_run_fails_without_knowledge_layer(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_repo_with_bugfix(repo)
    result = TasksStage().run(_ctx(repo, workspace))
    assert result.success is False
    assert "repo_graph" in (result.error or "")


def test_verify_true_after_run(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo_with_bugfix(repo)
    _seed_knowledge_layer(repo, workspace)
    stage = TasksStage()
    stage.execute(_ctx(repo, workspace))
    assert stage.verify(_ctx(repo, workspace)) is True


def test_second_run_is_cache_hit(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "ws"
    _seed_repo_with_bugfix(repo)
    _seed_knowledge_layer(repo, workspace)

    stage = TasksStage()
    ctx = _ctx(repo, workspace)
    first = stage.execute(ctx)
    second = stage.execute(ctx)
    assert first.success and second.success
    assert second.cache_hit is True
