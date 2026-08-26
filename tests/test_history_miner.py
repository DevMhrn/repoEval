"""Tests for pipeline.tasks.miners.history."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pipeline.tasks.miners.history import (
    HistoryCandidate,
    _infer_modules,
    _score,
    mine_history,
)


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout


def _seed_bugfix_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text(
        "def parse(s):\n    return s.upper()\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    # A qualifying bug-fix commit: touches both code and tests.
    (root / "pkg" / "core.py").write_text(
        "def parse(s):\n    return s.strip().upper()\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text(
        "from pkg.core import parse\n"
        "def test_strip_whitespace(): assert parse(' x') == 'X'\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix parse to strip surrounding whitespace")

    # A non-bugfix commit that shouldn't qualify.
    (root / "README.md").write_text("readme\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs: add readme")


def test_mines_bugfix_commit(tmp_path: Path):
    _seed_bugfix_repo(tmp_path)
    candidates = mine_history(tmp_path)
    subjects = [c.subject for c in candidates]
    assert any("fix parse" in s for s in subjects)


def test_diff_stats_recorded(tmp_path: Path):
    _seed_bugfix_repo(tmp_path)
    candidates = mine_history(tmp_path)
    bugfix = next(c for c in candidates if "fix parse" in c.subject)
    assert bugfix.diff_loc > 0
    assert any("pkg/core.py" in f for f in bugfix.files_changed)


def test_multi_file_bonus_in_score():
    c = HistoryCandidate(
        sha="x", parent_sha="y", subject="fix bug", date="", author="",
        files_changed=["a.py", "tests/test_a.py"],
        diff_loc=50, module_span=["a"], bugfix_score=0.7,
    )
    _score(c)
    assert "multi-file" in c.reasons
    assert c.score > 0.4


def test_issue_link_penalty():
    c1 = HistoryCandidate(
        sha="x", parent_sha="y", subject="fix bug", date="", author="",
        files_changed=["a.py"], diff_loc=50, bugfix_score=0.7,
    )
    c2 = HistoryCandidate(
        sha="x", parent_sha="y",
        subject="fix bug #123",
        date="", author="",
        files_changed=["a.py"], diff_loc=50, bugfix_score=0.7,
        has_issue_link=True,
    )
    _score(c1)
    _score(c2)
    assert c2.score < c1.score
    assert any("leak risk" in r for r in c2.reasons)


def test_infer_modules_from_paths():
    known = {"pkg.core", "pkg.util"}
    assert _infer_modules(["pkg/core.py", "pkg/util.py"], known) == {"pkg.core", "pkg.util"}


def test_infer_modules_strips_src_prefix():
    known = {"pkg.core"}
    assert _infer_modules(["src/pkg/core.py"], known) == {"pkg.core"}


def test_infer_modules_handles_init():
    known = {"pkg"}
    assert _infer_modules(["pkg/__init__.py"], known) == {"pkg"}


def test_limit_respected(tmp_path: Path):
    _seed_bugfix_repo(tmp_path)
    candidates = mine_history(tmp_path, limit=1)
    assert len(candidates) <= 1


def test_max_files_changed_filter_excludes_big_commits(tmp_path: Path):
    _seed_bugfix_repo(tmp_path)
    candidates = mine_history(tmp_path, max_files_changed=1)
    for c in candidates:
        assert len(c.files_changed) <= 1


def test_mine_gracefully_handles_non_git(tmp_path: Path):
    assert mine_history(tmp_path) == []


def test_module_span_populated_when_known_provided(tmp_path: Path):
    _seed_bugfix_repo(tmp_path)
    candidates = mine_history(tmp_path, known_module_ids={"pkg.core"})
    bugfix = next(c for c in candidates if "fix parse" in c.subject)
    assert "pkg.core" in bugfix.module_span
