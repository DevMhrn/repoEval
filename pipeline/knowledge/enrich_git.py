"""
Git enrichment.

Attaches commit metadata to graph nodes:

- Per file: last commit sha, ISO date, author, subject line.
- Per function (optional): list of commit shas whose change touched the
  function's line span.

Uses subprocess rather than GitPython to keep failure modes obvious
and the dependency surface small.

Per-function history is gated behind an explicit flag AND a node count
ceiling (``PER_FN_HISTORY_MAX_NODES``) because ``git log -L`` scales
poorly with repo history — running it 5000+ times can take minutes on
a real project. When mining actually needs it, we can enable it for
just the candidate function set.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .schema import Node, RepoGraph

PER_FN_HISTORY_MAX_NODES: int = 5000
_LAST_COMMIT_TIMEOUT_SEC: int = 30
_FN_HISTORY_TIMEOUT_SEC: int = 15


@dataclass
class _FileCommit:
    sha: str
    date: str
    author: str
    message: str


def enrich_with_git(
    graph: RepoGraph,
    repo_path: Path,
    *,
    per_function_history: bool = False,
) -> RepoGraph:
    file_commits = _collect_file_commits(graph, repo_path)

    enriched: list[Node] = []
    enable_fn_history = (
        per_function_history and len(graph.nodes) <= PER_FN_HISTORY_MAX_NODES
    )

    for node in graph.nodes:
        node_copy = node.model_copy(deep=True)
        commit = file_commits.get(node.file)
        if commit:
            git_meta: dict = {
                "last_commit": commit.sha,
                "last_date": commit.date,
                "last_author": commit.author,
                "last_message": commit.message,
            }
            if enable_fn_history and node.type in ("function", "method"):
                span_shas = _function_commit_shas(
                    repo_path, node.file, node.line, node.end_line
                )
                if span_shas:
                    git_meta["commits_touching_span"] = span_shas
            node_copy.metadata["git"] = git_meta
        enriched.append(node_copy)

    return graph.model_copy(update={"nodes": enriched})


def _collect_file_commits(
    graph: RepoGraph, repo_path: Path
) -> dict[str, _FileCommit]:
    files = sorted({n.file for n in graph.nodes if n.file})
    out: dict[str, _FileCommit] = {}
    for f in files:
        if f.startswith("<external>"):
            continue
        commit = _last_commit_for(repo_path, f)
        if commit:
            out[f] = commit
    return out


def _last_commit_for(repo_path: Path, file_path: str) -> _FileCommit | None:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                "-1",
                "--format=%H%x1f%aI%x1f%an%x1f%s",
                "--",
                file_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_LAST_COMMIT_TIMEOUT_SEC,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return None
    line = result.stdout.strip()
    if not line:
        return None
    parts = line.split("\x1f")
    if len(parts) != 4:
        return None
    sha, date, author, message = parts
    return _FileCommit(sha=sha, date=date, author=author, message=message)


def _function_commit_shas(
    repo_path: Path, file: str, start_line: int, end_line: int
) -> list[str]:
    if start_line < 1 or end_line < start_line:
        return []
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                f"-L{start_line},{end_line}:{file}",
                "--format=%H",
                "--no-patch",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_FN_HISTORY_TIMEOUT_SEC,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]
