"""Tests for pipeline.hygiene.ingest."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pipeline.hygiene.ingest import (
    IngestError,
    _classify,
    ingest,
)


def _seed_git_repo(path: Path, file_name: str = "a.txt", content: str = "hello\n") -> str:
    path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / file_name).write_text(content)
    subprocess.run(["git", "-C", str(path), "add", file_name], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
        env=env,
    )
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_classify_urls():
    assert _classify("https://github.com/x/y.git") == "url"
    assert _classify("http://github.com/x/y") == "url"
    assert _classify("git@github.com:x/y.git") == "url"
    assert _classify("ssh://git@x/y") == "url"


def test_classify_paths():
    assert _classify("/tmp/repo") == "path"
    assert _classify("./relative") == "path"
    assert _classify("~/x") == "path"


def test_ingest_local_git_repo(tmp_path: Path):
    src = tmp_path / "src"
    sha = _seed_git_repo(src)

    result = ingest(str(src), tmp_path / "ws")
    assert result.repo_path == tmp_path / "ws" / "repo"
    assert result.repo_path.exists()
    assert result.source_type == "path"
    assert result.resolved_commit == sha
    assert result.reused is False
    assert (result.repo_path / "a.txt").read_text() == "hello\n"


def test_ingest_local_plain_directory(tmp_path: Path):
    src = tmp_path / "plain"
    src.mkdir()
    (src / "note.md").write_text("no git here\n")

    result = ingest(str(src), tmp_path / "ws")
    assert result.repo_path.exists()
    assert (result.repo_path / ".git").exists()
    assert result.resolved_commit
    assert (result.repo_path / "note.md").read_text() == "no git here\n"


def test_ingest_is_idempotent_for_unchanged_source(tmp_path: Path):
    src = tmp_path / "src"
    _seed_git_repo(src)
    workspace = tmp_path / "ws"

    r1 = ingest(str(src), workspace)
    r2 = ingest(str(src), workspace)
    assert r2.reused is True
    assert r1.resolved_commit == r2.resolved_commit


def test_ingest_missing_source_raises(tmp_path: Path):
    with pytest.raises(IngestError, match="not found"):
        ingest(str(tmp_path / "nowhere"), tmp_path / "ws")


def test_ingest_file_source_raises(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("nope")
    with pytest.raises(IngestError, match="not a directory"):
        ingest(str(f), tmp_path / "ws")


def test_ingest_result_reports_source_and_type(tmp_path: Path):
    src = tmp_path / "src"
    _seed_git_repo(src)
    result = ingest(str(src), tmp_path / "ws")
    assert result.source == str(src)
    assert result.source_type == "path"
