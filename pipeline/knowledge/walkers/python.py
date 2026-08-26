"""
Python module discovery.

Walks a repo's ``.py`` files, parses each into :class:`ast.Module`, and
yields a :class:`ParsedModule` per file. Downstream extractors
(:mod:`pipeline.knowledge.extractors`) consume these to build graph
nodes and edges.

Skipping rules:

- VCS metadata (``.git``), virtualenvs, cache and build dirs are
  always excluded — see :data:`SKIP_DIR_NAMES`.
- ``skip_tests=True`` excludes anything whose dotted module id begins
  with a ``test`` component or has any segment matching
  ``test_*`` / ``*_test``.
- Syntax errors and undecodable files are logged (via the caller's
  logger, we just don't yield them) and never crash the walk.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".eggs",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
    }
)


@dataclass
class ParsedModule:
    path: Path
    module_id: str
    tree: ast.Module

    @property
    def is_test(self) -> bool:
        parts = self.module_id.split(".")
        return any(
            part == "tests"
            or part.startswith("test_")
            or part.endswith("_test")
            for part in parts
        )


def walk_python(
    repo_path: Path,
    *,
    source_roots: list[Path] | None = None,
    skip_tests: bool = False,
) -> Iterator[ParsedModule]:
    roots = source_roots or [repo_path]
    for root in roots:
        yield from _walk_root(root, repo_path, skip_tests=skip_tests)


def _walk_root(
    root: Path,
    repo_root: Path,
    *,
    skip_tests: bool,
) -> Iterator[ParsedModule]:
    if not root.exists() or not root.is_dir():
        return
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        module_id = _derive_module_id(path, repo_root)
        parsed = _parse(path, module_id)
        if parsed is None:
            continue
        if skip_tests and parsed.is_test:
            continue
        yield parsed


def _parse(path: Path, module_id: str) -> ParsedModule | None:
    try:
        source = path.read_text()
    except (UnicodeDecodeError, OSError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    return ParsedModule(path=path, module_id=module_id, tree=tree)


def _derive_module_id(path: Path, repo_root: Path) -> str:
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        rel = path
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else path.stem
