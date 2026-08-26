"""Tests for pipeline.tasks.builders.excision."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.tasks.builders.excision import (
    ExcisionBuildError,
    build_excision_task,
)
from pipeline.tasks.miners.excision import ExcisionCandidate


def _seed_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text(
        '"""core module."""\n\n'
        "def keep(a):\n"
        "    return a * 2\n"
        "\n"
        "def target(a, b):\n"
        '    """Add two numbers."""\n'
        "    result = a + b\n"
        "    return result\n"
    )


def _candidate() -> ExcisionCandidate:
    return ExcisionCandidate(
        node_id="pkg.core.target",
        file="pkg/core.py",
        line=6,
        end_line=9,
        signature="(a, b)",
        docstring="Add two numbers.",
        body_loc=3,
        line_rate=1.0,
        tests_ref_count=2,
    )


def test_solution_tree_is_pristine(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    solution_source = (artifact.solution_dir / "pkg" / "core.py").read_text()
    assert "return result" in solution_source
    assert "NotImplementedError" not in solution_source


def test_input_tree_has_body_replaced(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    input_source = (artifact.input_dir / "pkg" / "core.py").read_text()
    assert "NotImplementedError" in input_source
    assert "return result" not in input_source
    # Sibling function must be preserved.
    assert "def keep(a):" in input_source
    assert "return a * 2" in input_source
    # Docstring must be preserved for the target.
    assert "Add two numbers." in input_source


def test_input_signature_preserved(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    input_source = (artifact.input_dir / "pkg" / "core.py").read_text()
    assert "def target(a, b)" in input_source


def test_input_is_still_valid_python(tmp_path: Path):
    import ast

    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    ast.parse((artifact.input_dir / "pkg" / "core.py").read_text())


def test_verifier_includes_dockerfile_and_run_sh(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    assert (artifact.verifier_dir / "Dockerfile").exists()
    assert (artifact.verifier_dir / "run.sh").exists()


def test_verifier_copies_test_files_supplied(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    extra_test = tmp_path / "test_target.py"
    extra_test.write_text(
        "from pkg.core import target\n"
        "def test_add(): assert target(1, 2) == 3\n"
    )
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
        verifier_test_files=[extra_test],
    )
    copied = artifact.verifier_dir / "tests" / "test_target.py"
    assert copied.exists()
    assert "assert target(1, 2) == 3" in copied.read_text()


def test_task_json_records_provenance_and_module(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    data = json.loads(artifact.task_json_path.read_text())
    assert data["provenance"]["source"] == "excision"
    assert data["provenance"]["target_node_id"] == "pkg.core.target"
    assert data["module"] == "pkg.core"


def test_missing_function_raises(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    candidate = _candidate()
    candidate.node_id = "pkg.core.does_not_exist"
    with pytest.raises(ExcisionBuildError):
        build_excision_task(
            candidate,
            repo,
            tmp_path / "task_001",
            task_id="task_001",
            dockerfile_contents="FROM alpine\n",
        )


def test_git_directory_not_copied(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("[core]\n")

    artifact = build_excision_task(
        _candidate(),
        repo,
        tmp_path / "task_001",
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
    )
    assert not (artifact.input_dir / ".git").exists()
    assert not (artifact.solution_dir / ".git").exists()
