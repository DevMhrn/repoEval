"""
Introduce ruff + black configuration to the target repo and run auto-fix.

We install minimal configs — line length 100, Py 3.11 target, a
conservative rule selection — then run ``ruff check --fix`` and
``black``. The reproducibility gate in Phase 1.14 decides whether any
residual lint errors are acceptable for shipping; here we just report.

If the repo already has a ``[tool.black]`` section in ``pyproject.toml``
we leave it alone. Same for ``.ruff.toml`` — the pipeline is
non-destructive to existing config unless explicitly asked to overwrite.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RUFF_CONFIG = """\
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "I", "W", "UP", "B"]
ignore = ["E501"]
"""

BLACK_TOML_BLOCK = '\n[tool.black]\nline-length = 100\ntarget-version = ["py311"]\n'


@dataclass
class LintReport:
    ruff_config_path: Path
    black_config_path: Path
    ruff_fix_exit_code: int
    black_exit_code: int
    verify_exit_code: int
    residual_errors: int
    lint_clean: bool


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess]


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=cmd, returncode=127, stdout="", stderr="tool not found"
        )


def setup_lint(
    repo_path: Path,
    *,
    runner: CommandRunner | None = None,
    overwrite: bool = False,
) -> LintReport:
    run = runner or _default_runner

    ruff_config = _write_ruff_config(repo_path, overwrite=overwrite)
    black_config = _ensure_black_config(repo_path)

    fix = run(["ruff", "check", "--fix", str(repo_path)])
    black = run(["black", "--quiet", str(repo_path)])
    verify = run(["ruff", "check", str(repo_path)])

    residual = _count_ruff_errors(verify.stdout + verify.stderr)

    return LintReport(
        ruff_config_path=ruff_config,
        black_config_path=black_config,
        ruff_fix_exit_code=fix.returncode,
        black_exit_code=black.returncode,
        verify_exit_code=verify.returncode,
        residual_errors=residual,
        lint_clean=verify.returncode == 0 and residual == 0,
    )


def _write_ruff_config(repo_path: Path, *, overwrite: bool) -> Path:
    path = repo_path / ".ruff.toml"
    if path.exists() and not overwrite:
        return path
    path.write_text(RUFF_CONFIG)
    return path


def _ensure_black_config(repo_path: Path) -> Path:
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "[tool.black]" not in content:
            pyproject.write_text(content.rstrip() + BLACK_TOML_BLOCK)
    else:
        pyproject.write_text(BLACK_TOML_BLOCK.lstrip())
    return pyproject


def _count_ruff_errors(output: str) -> int:
    m = re.search(r"Found (\d+) error", output)
    if m:
        return int(m.group(1))
    if "All checks passed" in output:
        return 0
    return 0
