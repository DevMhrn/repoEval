"""
Validation harness orchestrator.

validate_task(task_folder) runs all four checks in order, aborts on the
first ERROR (setup failure), and writes a ValidationReport to the task's
evidence/ folder.

The report is machine-readable JSON so tasks.json can index every task's
validation status without re-running the harness.

Phase 0 status: STUB — implemented in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .checks import CheckResult


@dataclass
class ValidationReport:
    task_folder: Path
    checks: list[CheckResult]
    verdict: str
    determinism_repeats: int


def validate_task(task_folder: Path) -> ValidationReport:
    raise NotImplementedError("Phase 3")
