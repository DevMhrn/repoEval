"""Tests for pipeline.common.ecosystem and PythonStrategy."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.common.ecosystem import (
    EcosystemStrategy,
    UnsupportedEcosystemError,
    detect,
)
from pipeline.common.ecosystems.python import PythonStrategy


def test_detect_python_via_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    strategy = detect(tmp_path)
    assert isinstance(strategy, PythonStrategy)
    assert strategy.name == "python"


def test_detect_python_via_setup_py(tmp_path: Path):
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    assert isinstance(detect(tmp_path), PythonStrategy)


def test_detect_python_via_setup_cfg(tmp_path: Path):
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = x\n")
    assert isinstance(detect(tmp_path), PythonStrategy)


def test_detect_python_via_requirements_txt(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    assert isinstance(detect(tmp_path), PythonStrategy)


def test_detect_python_via_alternate_requirements(tmp_path: Path):
    (tmp_path / "requirements-dev.txt").write_text("pytest\n")
    assert isinstance(detect(tmp_path), PythonStrategy)


def test_detect_empty_directory_raises(tmp_path: Path):
    with pytest.raises(UnsupportedEcosystemError):
        detect(tmp_path)


def test_python_strategy_dockerfile_base_default():
    assert PythonStrategy().dockerfile_base() == "python:3.11-slim"


def test_python_strategy_install_cmd_uses_lockfile():
    assert PythonStrategy().install_cmd() == [
        "pip",
        "install",
        "--no-cache-dir",
        "-r",
        "requirements.lock",
    ]


def test_python_strategy_test_cmd_default_and_selection():
    s = PythonStrategy()
    assert s.test_cmd() == ["pytest"]
    selected = s.test_cmd(["tests/test_a.py::test_x", "tests/test_b.py"])
    assert selected == [
        "pytest",
        "tests/test_a.py::test_x",
        "tests/test_b.py",
    ]


def test_discover_finds_top_level_tests_dir(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing.py").write_text("def test_x(): pass\n")
    paths = PythonStrategy().discover_test_paths(tmp_path)
    assert tmp_path / "tests" in paths
    assert tmp_path / "tests" / "test_thing.py" in paths


def test_discover_skips_venv_and_pycache(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "test_ignored.py").write_text("pass\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test_cached.py").write_text("pass\n")
    (tmp_path / "test_real.py").write_text("pass\n")

    paths = PythonStrategy().discover_test_paths(tmp_path)
    posix_paths = [p.as_posix() for p in paths]
    assert any(p.endswith("/test_real.py") for p in posix_paths)
    assert not any(".venv" in p for p in posix_paths)
    assert not any("__pycache__" in p for p in posix_paths)


def test_discover_returns_sorted_paths(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "test_z.py").write_text("pass\n")
    (tmp_path / "test_a.py").write_text("pass\n")
    (tmp_path / "test_m.py").write_text("pass\n")
    paths = PythonStrategy().discover_test_paths(tmp_path)
    posix_paths = [p.as_posix() for p in paths]
    assert posix_paths == sorted(posix_paths)


def test_ecosystem_strategy_is_abstract():
    with pytest.raises(TypeError):
        EcosystemStrategy()  # type: ignore[abstract]


def test_registry_is_idempotent_across_repeated_detects(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    from pipeline.common import ecosystem as eco

    detect(tmp_path)
    count = len(eco._REGISTRY)
    detect(tmp_path)
    assert len(eco._REGISTRY) == count
