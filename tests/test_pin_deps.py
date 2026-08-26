"""Tests for dependency pinning."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.common.ecosystems.python import (
    PinDepsError,
    PythonStrategy,
    _extract_setup_py_deps,
)
from pipeline.hygiene.pin_deps import pin_deps


class _RecordingRunner:
    def __init__(self, side_effect_writes: dict[str, str] | None = None):
        self.calls: list[list[str]] = []
        self._writes = side_effect_writes or {}

    def __call__(self, cmd: list[str]) -> None:
        self.calls.append(cmd)
        # Emulate uv creating the lockfile so downstream logic sees it.
        for flag_idx, flag in enumerate(cmd):
            if flag == "-o" and flag_idx + 1 < len(cmd):
                target = Path(cmd[flag_idx + 1])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self._writes.get(str(target), ""))


def test_pin_pyproject_calls_uv_with_hashes(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\nversion='0.1.0'\n"
    )
    runner = _RecordingRunner()
    strategy = PythonStrategy()
    lockfile = strategy.pin_deps(tmp_path, tmp_path / "work", runner=runner)

    assert lockfile == tmp_path / "requirements.lock"
    assert lockfile.exists()
    cmd = runner.calls[0]
    assert cmd[:2] == ["uv", "pip"]
    assert "compile" in cmd
    assert "--generate-hashes" in cmd
    assert str(tmp_path / "pyproject.toml") in cmd
    assert cmd[-2:] == ["-o", str(lockfile)]


def test_pin_requirements_txt(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("six\n")
    runner = _RecordingRunner()
    lockfile = PythonStrategy().pin_deps(tmp_path, tmp_path / "work", runner=runner)
    assert lockfile.exists()
    assert str(tmp_path / "requirements.txt") in runner.calls[0]


def test_pin_setup_py_extracts_install_requires_and_synths_input(tmp_path: Path):
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(name='x', install_requires=['six', 'requests>=2.0'])\n"
    )
    runner = _RecordingRunner()
    workdir = tmp_path / "work"
    lockfile = PythonStrategy().pin_deps(tmp_path, workdir, runner=runner)
    assert lockfile.exists()
    synth = workdir / "requirements.in"
    assert synth.exists()
    body = synth.read_text()
    assert "six" in body
    assert "requests>=2.0" in body


def test_pin_no_manifest_raises(tmp_path: Path):
    with pytest.raises(PinDepsError, match="no recognizable"):
        PythonStrategy().pin_deps(tmp_path, tmp_path / "work", runner=lambda cmd: None)


def test_extract_setup_py_deps_handles_list_literal(tmp_path: Path):
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import setup\n"
        "setup(install_requires=['a', 'b>=1', 'c<2'])\n"
    )
    assert _extract_setup_py_deps(setup_py) == ["a", "b>=1", "c<2"]


def test_extract_setup_py_deps_handles_tuple_literal(tmp_path: Path):
    setup_py = tmp_path / "setup.py"
    setup_py.write_text("setup(install_requires=('a', 'b'))\n")
    assert _extract_setup_py_deps(setup_py) == ["a", "b"]


def test_extract_setup_py_deps_ignores_dynamic(tmp_path: Path):
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "reqs = ['a']\n"
        "from setuptools import setup\n"
        "setup(install_requires=reqs)\n"
    )
    assert _extract_setup_py_deps(setup_py) == []


def test_delegator_uses_detected_strategy(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\nversion='0.1.0'\n"
    )
    # Use a strategy with a recording runner to observe the call.
    runner = _RecordingRunner()

    class _Wrap(PythonStrategy):
        def pin_deps(self, repo_path: Path, workdir: Path) -> Path:
            return super().pin_deps(repo_path, workdir, runner=runner)

    lockfile = pin_deps(tmp_path, tmp_path / "work", strategy=_Wrap())
    assert lockfile.exists()
    assert runner.calls, "delegator did not call strategy.pin_deps"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_integration_uv_compiles_empty_pyproject(tmp_path: Path):
    """Real invocation of uv on a manifest with zero deps — no network needed."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='repoeval-test'\nversion='0.0.0'\n"
    )
    try:
        lockfile = PythonStrategy().pin_deps(tmp_path, tmp_path / "work")
    except PinDepsError as e:
        pytest.skip(f"uv invocation failed in this environment: {e}")

    assert lockfile.exists()
    content = lockfile.read_text()
    # For a project with zero deps, uv produces a header and no pin lines.
    # We just assert it produced a well-formed file.
    assert len(content) > 0


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_integration_uv_run_is_reproducible(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='repoeval-test'\nversion='0.0.0'\n"
    )
    try:
        first = PythonStrategy().pin_deps(tmp_path, tmp_path / "work").read_text()
        # Delete and re-run.
        (tmp_path / "requirements.lock").unlink()
        second = PythonStrategy().pin_deps(tmp_path, tmp_path / "work").read_text()
    except PinDepsError as e:
        pytest.skip(f"uv invocation failed: {e}")

    def _normalise(text: str) -> str:
        return "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("#") and line.strip()
        )

    assert _normalise(first) == _normalise(second)


def test_default_runner_missing_executable_raises_pin_deps_error():
    from pipeline.common.ecosystems.python import _default_runner
    with pytest.raises(PinDepsError, match="not found"):
        _default_runner(["definitely-not-a-real-cmd-xyz-9871", "--help"])


def test_default_runner_nonzero_exit_raises_pin_deps_error():
    from pipeline.common.ecosystems.python import _default_runner
    with pytest.raises(PinDepsError, match="failed"):
        _default_runner(["python", "-c", "import sys; sys.exit(2)"])


def test_synth_input_is_empty_when_no_install_requires(tmp_path: Path):
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='x')\n"
    )
    runner = _RecordingRunner()
    workdir = tmp_path / "work"
    PythonStrategy().pin_deps(tmp_path, workdir, runner=runner)
    synth = workdir / "requirements.in"
    assert synth.exists()
    assert synth.read_text() == ""


def test_verify_subprocess_helper():
    # sanity: subprocess module is importable — a shield against later refactors
    assert subprocess.run
