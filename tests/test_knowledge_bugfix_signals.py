"""Tests for pipeline.knowledge.bugfix_signals."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pipeline.knowledge.bugfix_signals import (
    _is_test_file,
    _parse_git_log,
    _signal_from_entry,
    scan_bugfix_commits,
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


def test_is_test_file_recognises_common_shapes():
    assert _is_test_file("tests/test_x.py")
    assert _is_test_file("pkg/tests/util.py")
    assert _is_test_file("test/test_x.py")
    assert _is_test_file("test_foo.py")
    assert _is_test_file("foo_test.py")
    assert not _is_test_file("pkg/core.py")
    assert not _is_test_file("readme.md")


def test_signal_scoring_message_only():
    entry = {
        "sha": "a",
        "date": "d",
        "author": "x",
        "subject": "Fix broken parser",
        "files": ["pkg/core.py"],
    }
    signal = _signal_from_entry(entry)
    assert signal.is_bugfix is True
    assert signal.bugfix_score == 0.7  # 0.6 + 0.1 (code only)


def test_signal_scoring_test_plus_code_bumps():
    entry = {
        "sha": "a",
        "date": "d",
        "author": "x",
        "subject": "Fix regression in encoder",
        "files": ["pkg/core.py", "tests/test_core.py"],
    }
    signal = _signal_from_entry(entry)
    assert signal.bugfix_score == 1.0
    assert signal.is_bugfix is True


def test_signal_scoring_no_message_hit():
    entry = {
        "sha": "a",
        "date": "d",
        "author": "x",
        "subject": "Refactor internals for readability",
        "files": ["pkg/core.py"],
    }
    signal = _signal_from_entry(entry)
    assert signal.is_bugfix is False
    assert signal.bugfix_score < 0.6


def test_signal_ambiguous_but_message_dominant():
    entry = {
        "sha": "a",
        "date": "d",
        "author": "x",
        "subject": "resolve crash on empty input",
        "files": ["pkg/core.py", "tests/test_core.py"],
    }
    # 'crash' is in the pattern
    signal = _signal_from_entry(entry)
    assert signal.is_bugfix is True
    assert signal.bugfix_score == 1.0


def test_parse_git_log_returns_entries_in_order():
    text = (
        "commit\x1fsha1\x1f2026-01-01\x1fAlice\x1ffix: bug\n"
        "a.py\n"
        "commit\x1fsha2\x1f2026-01-02\x1fBob\x1fadd feature\n"
        "b.py\n"
        "tests/test_b.py\n"
    )
    entries = _parse_git_log(text)
    assert len(entries) == 2
    assert entries[0]["sha"] == "sha1"
    assert entries[0]["files"] == ["a.py"]
    assert entries[1]["files"] == ["b.py", "tests/test_b.py"]


def _seed_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    (root / "core.py").write_text("def a(): pass\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial: add core")

    (root / "core.py").write_text("def a(): return 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text(
        "from core import a\ndef test_a(): assert a() == 1\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix null return in core")

    (root / "docs.md").write_text("# docs\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs: initial")


def test_scan_bugfix_commits_e2e(tmp_path: Path):
    _seed_repo(tmp_path)
    signals = scan_bugfix_commits(tmp_path)
    assert len(signals) == 3

    subjects = [s.subject for s in signals]
    assert any("fix null return" in s for s in subjects)

    bugfix = [s for s in signals if s.is_bugfix]
    assert len(bugfix) >= 1
    assert bugfix[0].bugfix_score >= 0.6


def test_scan_gracefully_handles_non_git_dir(tmp_path: Path):
    assert scan_bugfix_commits(tmp_path) == []
