"""
Python ecosystem strategy.

Detects Python repos by the presence of PEP-standard manifests or a
``requirements*.txt`` at the repo root. Provides commands and metadata
for downstream hygiene steps. Dependency pinning shells out to ``uv``
because it's the fastest deterministic resolver we've got and produces
a fully-hashed lockfile in one shot.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, TypeAlias

from ..ecosystem import EcosystemStrategy, register


class PinDepsError(Exception):
    """Raised when dependency pinning fails."""


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

    def pin_deps(
        self,
        repo_path: Path,
        workdir: Path,
        *,
        uv_cmd: str = "uv",
        runner: SubprocessRunner | None = None,
    ) -> Path:
        """Produce ``requirements.lock`` in ``repo_path``. Returns its path.

        ``uv_cmd`` and ``runner`` are seams for tests. In production both
        are omitted and we shell out to the ``uv`` binary on ``PATH``.
        """
        lockfile = repo_path / "requirements.lock"
        run = runner or _default_runner

        pyproject = repo_path / "pyproject.toml"
        reqs = sorted(repo_path.glob(self._REQUIREMENTS_GLOB))
        setup_py = repo_path / "setup.py"

        if pyproject.exists():
            run(
                [
                    uv_cmd,
                    "pip",
                    "compile",
                    "--generate-hashes",
                    str(pyproject),
                    "-o",
                    str(lockfile),
                ]
            )
            return lockfile

        if reqs:
            run(
                [
                    uv_cmd,
                    "pip",
                    "compile",
                    "--generate-hashes",
                    str(reqs[0]),
                    "-o",
                    str(lockfile),
                ]
            )
            return lockfile

        if setup_py.exists():
            deps = _extract_setup_py_deps(setup_py)
            workdir.mkdir(parents=True, exist_ok=True)
            synth = workdir / "requirements.in"
            synth.write_text(("\n".join(deps) + "\n") if deps else "")
            run(
                [
                    uv_cmd,
                    "pip",
                    "compile",
                    "--generate-hashes",
                    str(synth),
                    "-o",
                    str(lockfile),
                ]
            )
            return lockfile

        raise PinDepsError(f"no recognizable python manifest in {repo_path}")

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


SubprocessRunner: TypeAlias = Callable[[list[str]], None]


def _default_runner(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise PinDepsError(
            f"command failed: {' '.join(cmd)}\n{e.stderr or e.stdout}"
        ) from e
    except FileNotFoundError as e:
        raise PinDepsError(
            f"executable not found: {cmd[0]} (is uv installed?)"
        ) from e


def _extract_setup_py_deps(setup_py: Path) -> list[str]:
    """Statically extract ``install_requires`` literal from setup.py.

    We only accept a list/tuple of string literals. Anything dynamic
    (list comprehensions, function calls) is ignored — we never exec
    setup.py because that could run arbitrary code.
    """
    try:
        tree = ast.parse(setup_py.read_text())
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "install_requires" and isinstance(
                kw.value, ast.List | ast.Tuple
            ):
                return [
                    element.value
                    for element in kw.value.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                ]
    return []
