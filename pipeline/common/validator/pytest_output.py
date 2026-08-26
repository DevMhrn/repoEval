"""
Pytest output parser used by :func:`fail_before` to distinguish real
behavioral test failures from import / collection errors.

The parser is deliberately lightweight — pytest's exact wording drifts
between versions, so we match a small set of stable markers rather than
a strict grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ASSERTION_MARKERS: tuple[str, ...] = (
    "AssertionError",
    "assert ",
    "assert(",
    "assert not ",
)

_COLLECTION_ERROR_MARKERS: tuple[str, ...] = (
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "errors during collection",
    "error during collection",
    "InternalError",
    "conftest error",
    "IndentationError",
)

_SUMMARY_RE = re.compile(
    r"^=+.*(passed|failed|error|skipped).*in\s+[\d.]+\s*s.*=+$"
)


@dataclass
class PytestOutcome:
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    has_assertion_failure: bool = False
    has_collection_error: bool = False
    failure_lines: list[str] = field(default_factory=list)


def parse_pytest_output(output: str) -> PytestOutcome:
    outcome = PytestOutcome()

    summary_line = _find_summary_line(output)
    if summary_line:
        for pattern, attr in (
            (r"(\d+)\s+passed", "passed"),
            (r"(\d+)\s+failed", "failed"),
            (r"(\d+)\s+error", "errored"),
            (r"(\d+)\s+skipped", "skipped"),
        ):
            match = re.search(pattern, summary_line)
            if match:
                setattr(outcome, attr, int(match.group(1)))

    outcome.has_assertion_failure = any(
        marker in output for marker in _ASSERTION_MARKERS
    )
    outcome.has_collection_error = any(
        marker in output for marker in _COLLECTION_ERROR_MARKERS
    )

    for line in output.splitlines():
        if line.startswith(("FAILED ", "ERROR ")):
            outcome.failure_lines.append(line.strip())

    return outcome


def _find_summary_line(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        if _SUMMARY_RE.match(line):
            return line
    return None
