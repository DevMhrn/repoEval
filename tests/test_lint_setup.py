"""Tests for pipeline.hygiene.lint_setup."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.hygiene.lint_setup import (
    BLACK_TOML_BLOCK,
    RUFF_CONFIG,
    LintReport,
    setup_lint,
)


class _RecordingRunner:
    def __init__(self, verify_output: str = "All checks passed!\n", verify_rc: int = 0):
        self.calls: list[list[str]] = []
        self._verify_output = verify_output
        self._verify_rc = verify_rc

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        # third call is verify (check without --fix)
        is_verify = "check" in cmd and "--fix" not in cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=self._verify_rc if is_verify else 0,
            stdout=self._verify_output if is_verify else "",
            stderr="",
        )


def test_writes_ruff_config(tmp_path: Path):
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    assert (tmp_path / ".ruff.toml").exists()
    assert (tmp_path / ".ruff.toml").read_text() == RUFF_CONFIG


def test_writes_black_config_to_new_pyproject(tmp_path: Path):
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    pyproject = tmp_path / "pyproject.toml"
    assert pyproject.exists()
    assert "[tool.black]" in pyproject.read_text()


def test_appends_black_config_to_existing_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    content = (tmp_path / "pyproject.toml").read_text()
    assert "[project]" in content
    assert "[tool.black]" in content


def test_leaves_existing_black_config_alone(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\n\n[tool.black]\nline-length = 88\n"
    )
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    content = (tmp_path / "pyproject.toml").read_text()
    assert "line-length = 88" in content
    assert BLACK_TOML_BLOCK.strip() not in content


def test_leaves_existing_ruff_config_alone(tmp_path: Path):
    existing = "line-length = 88\n"
    (tmp_path / ".ruff.toml").write_text(existing)
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    assert (tmp_path / ".ruff.toml").read_text() == existing


def test_overwrite_flag_replaces_ruff_config(tmp_path: Path):
    (tmp_path / ".ruff.toml").write_text("old\n")
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner, overwrite=True)
    assert (tmp_path / ".ruff.toml").read_text() == RUFF_CONFIG


def test_invokes_ruff_fix_then_black_then_ruff_check(tmp_path: Path):
    runner = _RecordingRunner()
    setup_lint(tmp_path, runner=runner)
    assert len(runner.calls) == 3
    assert runner.calls[0][0:3] == ["ruff", "check", "--fix"]
    assert runner.calls[1][0] == "black"
    assert runner.calls[2][0:2] == ["ruff", "check"]
    assert "--fix" not in runner.calls[2]


def test_report_indicates_lint_clean_when_verify_passes(tmp_path: Path):
    runner = _RecordingRunner(verify_output="All checks passed!\n", verify_rc=0)
    report = setup_lint(tmp_path, runner=runner)
    assert isinstance(report, LintReport)
    assert report.lint_clean is True
    assert report.residual_errors == 0


def test_report_indicates_residual_errors(tmp_path: Path):
    runner = _RecordingRunner(
        verify_output="Found 3 errors.\n",
        verify_rc=1,
    )
    report = setup_lint(tmp_path, runner=runner)
    assert report.lint_clean is False
    assert report.residual_errors == 3


def test_missing_tool_reports_gracefully(tmp_path: Path):
    def runner(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=cmd, returncode=127, stdout="", stderr="tool not found"
        )
    report = setup_lint(tmp_path, runner=runner)
    assert report.lint_clean is False
    assert report.ruff_fix_exit_code == 127
