"""
Repo ingestion.

Turn a source specifier (URL or local path) into a mutable workspace
copy on disk. The result is a git repository at ``workspace/repo/`` from
which the rest of the hygiene pipeline reads.

- **URL**  → ``git clone --depth <N> <url> workspace/repo``. Depth 100
  by default; the history miner in Phase 3.7 deepens on demand.
- **Path** → ``shutil.copytree(path, workspace/repo)``. If the copied
  tree isn't already a git repo, we ``git init`` and record a single
  ingest snapshot commit so downstream stages can rely on ``HEAD``.

Idempotency: if ``workspace/repo/.git/HEAD`` resolves to the same
commit as the source we return without touching the tree, marked
``reused=True``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

SourceType = Literal["url", "path"]

_DEFAULT_CLONE_DEPTH = 100


class IngestError(Exception):
    """Raised when ingestion fails or the source is unusable."""


@dataclass
class IngestResult:
    repo_path: Path
    source: str
    source_type: SourceType
    resolved_commit: str
    reused: bool


def ingest(
    source: str,
    workspace: Path,
    *,
    clone_depth: int = _DEFAULT_CLONE_DEPTH,
) -> IngestResult:
    repo_path = workspace / "repo"
    source_type = _classify(source)

    if repo_path.exists() and (repo_path / ".git").exists():
        current = _current_head(repo_path)
        if source_type == "path":
            src_path = Path(source).expanduser().resolve()
            if (src_path / ".git").exists() and current == _current_head(src_path):
                return IngestResult(
                    repo_path, source, source_type, current, reused=True
                )
            if not (src_path / ".git").exists():
                return IngestResult(
                    repo_path, source, source_type, current, reused=True
                )
        else:
            return IngestResult(
                repo_path, source, source_type, current, reused=True
            )

    workspace.mkdir(parents=True, exist_ok=True)
    if repo_path.exists():
        shutil.rmtree(repo_path)

    if source_type == "url":
        _clone(source, repo_path, depth=clone_depth)
    else:
        _copy_and_init(source, repo_path)

    return IngestResult(
        repo_path=repo_path,
        source=source,
        source_type=source_type,
        resolved_commit=_current_head(repo_path),
        reused=False,
    )


def _classify(source: str) -> SourceType:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https", "ssh", "git"}:
        return "url"
    if source.startswith("git@") or (parsed.scheme == "" and source.endswith(".git")):
        return "url"
    return "path"


def _clone(url: str, dest: Path, *, depth: int) -> None:
    _run_git(["git", "clone", "--depth", str(depth), url, str(dest)])


def _copy_and_init(source_path: str, dest: Path) -> None:
    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        raise IngestError(f"source path not found: {source_path}")
    if not src.is_dir():
        raise IngestError(f"source path is not a directory: {source_path}")

    shutil.copytree(src, dest, symlinks=True)

    if (dest / ".git").exists():
        return

    _run_git(["git", "init", "-q", str(dest)])
    _run_git(["git", "-C", str(dest), "add", "-A"])
    _run_git(
        [
            "git",
            "-C",
            str(dest),
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "ingest snapshot",
        ],
        env={
            "GIT_AUTHOR_NAME": "repoeval",
            "GIT_AUTHOR_EMAIL": "repoeval@localhost",
            "GIT_COMMITTER_NAME": "repoeval",
            "GIT_COMMITTER_EMAIL": "repoeval@localhost",
        },
    )


def _current_head(repo: Path) -> str:
    result = _run_git(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture=True,
    )
    return result.stdout.strip()


def _run_git(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    merged_env = None
    if env is not None:
        merged_env = {**os.environ, **env}
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture,
            text=True,
            env=merged_env,
        )
    except subprocess.CalledProcessError as e:
        raise IngestError(
            f"git command failed: {' '.join(cmd)}: {e.stderr or e}"
        ) from e
    except FileNotFoundError as e:
        raise IngestError("git is not installed or not on PATH") from e
