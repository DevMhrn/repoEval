"""
Smoke tests for Phase 0.

Verifies the scaffold is importable and the CLI wires up. Zero real
pipeline behavior tested here — that comes in Phase 1+.
"""

from __future__ import annotations

import subprocess
import sys


def test_pipeline_package_imports():
    import pipeline  # noqa: F401
    from pipeline import cli  # noqa: F401
    from pipeline.common import stage  # noqa: F401
    from pipeline.common.validator import harness  # noqa: F401
    from pipeline.hygiene import stage as hygiene_stage  # noqa: F401
    from pipeline.knowledge import stage as knowledge_stage  # noqa: F401
    from pipeline.tasks import stage as tasks_stage  # noqa: F401


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "hygiene" in result.stdout
    assert "knowledge" in result.stdout
    assert "tasks" in result.stdout


def test_cli_no_command_prints_help_and_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_cli_dispatches_to_stub():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.cli", "hygiene", "/tmp/fake-repo"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "hygiene" in result.stdout.lower()
    assert "phase 0" in result.stdout.lower()
