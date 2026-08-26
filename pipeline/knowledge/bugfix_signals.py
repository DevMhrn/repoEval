"""
Bug-fix commit signal detection.

Scans recent git history and returns a :class:`BugfixSignal` per
commit. The signal is a compound of two heuristics:

1. **Message pattern.** Word-boundary match on typical bug-fix
   vocabulary (``fix``, ``bug``, ``regress``, ``crash``, ``hang``,
   ``leak``, ``null``, etc.).
2. **Test-plus-code ratio.** A commit that changes at least one test
   file AND at least one non-test file is a strong signal — that's
   what most real bug fixes look like: reproduce with a test, fix in
   the code.

Signals feed :mod:`pipeline.tasks.miners.history` in Phase 3.7.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_BUGFIX_PATTERN = re.compile(
    r"\b(fix|bug|regress|regression|error|crash|hang|deadlock|"
    r"null|nullptr|leak|corrupt|broke|broken|invalid|panic)\b",
    re.IGNORECASE,
)

_DEFAULT_MAX_COMMITS: int = 500
_GIT_LOG_TIMEOUT_SEC: int = 60


@dataclass
class BugfixSignal:
    sha: str
    date: str
    author: str
    subject: str
    is_bugfix: bool
    bugfix_score: float
    files_changed: list[str] = field(default_factory=list)


def scan_bugfix_commits(
    repo_path: Path,
    *,
    max_commits: int = _DEFAULT_MAX_COMMITS,
) -> list[BugfixSignal]:
    entries = _read_git_log(repo_path, max_commits)
    return [_signal_from_entry(entry) for entry in entries]


def _read_git_log(repo_path: Path, max_commits: int) -> list[dict]:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                f"-{max_commits}",
                "--format=commit\x1f%H\x1f%aI\x1f%an\x1f%s",
                "--name-only",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_GIT_LOG_TIMEOUT_SEC,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return []
    return _parse_git_log(result.stdout)


def _parse_git_log(text: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("commit\x1f"):
            if current is not None:
                entries.append(current)
            parts = line.split("\x1f")
            if len(parts) < 5:
                current = None
                continue
            _, sha, date, author, subject = parts
            current = {
                "sha": sha,
                "date": date,
                "author": author,
                "subject": subject,
                "files": [],
            }
        elif line and current is not None:
            current["files"].append(line)
    if current is not None:
        entries.append(current)
    return entries


def _signal_from_entry(entry: dict) -> BugfixSignal:
    subject: str = entry["subject"]
    files: list[str] = entry["files"]

    msg_hit = bool(_BUGFIX_PATTERN.search(subject))
    has_test_file = any(_is_test_file(f) for f in files)
    has_code_file = any(not _is_test_file(f) for f in files)

    score = 0.0
    if msg_hit:
        score += 0.6
    if has_test_file and has_code_file:
        score += 0.4
    elif has_test_file or has_code_file:
        score += 0.1

    return BugfixSignal(
        sha=entry["sha"],
        date=entry["date"],
        author=entry["author"],
        subject=subject,
        is_bugfix=score >= 0.6,
        bugfix_score=round(score, 2),
        files_changed=files,
    )


def _is_test_file(path: str) -> bool:
    parts = path.split("/")
    for part in parts:
        if part in ("tests", "test"):
            return True
        if part.startswith("test_") or part.endswith("_test.py"):
            return True
    return False
