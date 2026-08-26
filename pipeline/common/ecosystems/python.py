"""
Python ecosystem strategy.

Detects Python repos by the presence of PEP-standard manifests or a
``requirements*.txt`` at the repo root. Provides commands and metadata
for downstream hygiene steps; the actual dependency pinning lands in
Phase 1.8 via ``pin_deps``.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ..ecosystem import EcosystemStrategy, register


@register
class PythonStrategy(EcosystemStrategy):
    name = "python"

    _MANIFEST_FILES: ClassVar[tuple[str, ...]] = (
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
    )

    _REQUIREMENTS_GLOB: ClassVar[str] = "requirements*.txt"

    _TEST_DIR_NAMES: ClassVar[tuple[str, ...]] = ("tests", "test")

    _SKIP_DIR_NAMES: ClassVar[frozenset[str]] = frozenset(
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
        }
    )

    def detect(self, repo_path: Path) -> bool:
        for name in self._MANIFEST_FILES:
            if (repo_path / name).is_file():
                return True
        for path in repo_path.glob(self._REQUIREMENTS_GLOB):
            if path.is_file():
                return True
        return False

    def pin_deps(self, repo_path: Path, workdir: Path) -> Path:
        raise NotImplementedError("Phase 1.8")

    def install_cmd(self) -> list[str]:
        return ["pip", "install", "--no-cache-dir", "-r", "requirements.lock"]

    def test_cmd(self, test_selection: list[str] | None = None) -> list[str]:
        cmd = ["pytest"]
        if test_selection:
            cmd.extend(test_selection)
        return cmd

    def dockerfile_base(self) -> str:
        return "python:3.11-slim"

    def discover_test_paths(self, repo_path: Path) -> list[Path]:
        found: set[Path] = set()

        for d in self._TEST_DIR_NAMES:
            candidate = repo_path / d
            if candidate.is_dir():
                found.add(candidate)

        for candidate in repo_path.rglob("test_*.py"):
            if not candidate.is_file():
                continue
            if any(part in self._SKIP_DIR_NAMES for part in candidate.parts):
                continue
            found.add(candidate)

        return sorted(found, key=lambda p: p.as_posix())
