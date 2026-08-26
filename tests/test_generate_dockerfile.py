"""Tests for pipeline.hygiene.generate_dockerfile."""

from __future__ import annotations

from pathlib import Path

from pipeline.common.ecosystems.python import PythonStrategy
from pipeline.hygiene.generate_dockerfile import generate_dockerfile


def test_generated_dockerfile_uses_strategy_base(tmp_path: Path):
    dockerfile = generate_dockerfile(tmp_path, PythonStrategy())
    assert dockerfile == tmp_path / "Dockerfile"
    content = dockerfile.read_text()
    assert content.startswith("FROM python:3.11-slim\n")


def test_generated_dockerfile_base_override(tmp_path: Path):
    dockerfile = generate_dockerfile(
        tmp_path,
        PythonStrategy(),
        base="python:3.12-alpine",
    )
    assert "FROM python:3.12-alpine" in dockerfile.read_text()


def test_dockerfile_installs_pytest_at_build_time(tmp_path: Path):
    content = generate_dockerfile(tmp_path, PythonStrategy()).read_text()
    assert "pytest" in content
    assert "pytest-cov" in content
    assert "pytest-json-report" in content


def test_dockerfile_installs_from_lockfile(tmp_path: Path):
    content = generate_dockerfile(tmp_path, PythonStrategy()).read_text()
    assert "requirements.lock" in content
    assert "pip install --no-cache-dir -r /tmp/requirements.lock" in content


def test_dockerfile_sets_pythonpath_for_src_layout(tmp_path: Path):
    content = generate_dockerfile(tmp_path, PythonStrategy()).read_text()
    assert "PYTHONPATH=/app/src:/app" in content


def test_dockerfile_writes_container_built_marker(tmp_path: Path):
    content = generate_dockerfile(tmp_path, PythonStrategy()).read_text()
    assert "/tmp/.container_built" in content


def test_dockerfile_is_deterministic(tmp_path: Path):
    a = generate_dockerfile(tmp_path, PythonStrategy())
    first = a.read_text()
    a.unlink()
    b = generate_dockerfile(tmp_path, PythonStrategy())
    assert b.read_text() == first


def test_dockerfile_apt_cleanup_included(tmp_path: Path):
    content = generate_dockerfile(tmp_path, PythonStrategy()).read_text()
    assert "rm -rf /var/lib/apt/lists/*" in content
    assert "--no-install-recommends" in content
