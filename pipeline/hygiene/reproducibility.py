"""
Twice-in-a-row reproducibility gate.

Runs a container command twice, normalises volatile output (timestamps,
durations, hex hashes), and asserts byte-identical results. That's the
acceptance bar from the assignment: two identical runs on the same
image must produce identical verdicts.

Normalisation is targeted at pytest's standard output shape. Any
callers with weirder output patterns should extend :data:`VOLATILE_PATTERNS`.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..common.docker_utils import RunResult, run_container

VOLATILE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bin\s+\d+\.\d+s\b"),
    re.compile(r"\d+\.\d+s"),
    re.compile(r"\b[0-9a-f]{32,}\b"),
    re.compile(r"session-\d+"),
    re.compile(r"20\d{2}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}"),
    re.compile(r"/tmp/[a-zA-Z0-9_.-]+"),
]


@dataclass
class ReproducibilityReport:
    passed: bool
    first_hash: str
    second_hash: str
    diff: str = ""


ContainerRunner = Callable[..., RunResult]


def check(
    image: str,
    cmd: list[str] | str,
    *,
    mounts: dict[Path, str] | None = None,
    runner: ContainerRunner | None = None,
) -> ReproducibilityReport:
    _run = runner or run_container
    first = _run(image, cmd, mounts=mounts)
    second = _run(image, cmd, mounts=mounts)

    a = _normalise(first.stdout)
    b = _normalise(second.stdout)

    ha = hashlib.sha256(a.encode()).hexdigest()[:16]
    hb = hashlib.sha256(b.encode()).hexdigest()[:16]

    if a == b:
        return ReproducibilityReport(passed=True, first_hash=ha, second_hash=hb)

    diff = "\n".join(
        difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="")
    )
    return ReproducibilityReport(
        passed=False, first_hash=ha, second_hash=hb, diff=diff
    )


def _normalise(text: str) -> str:
    for pattern in VOLATILE_PATTERNS:
        text = pattern.sub("<X>", text)
    return text
