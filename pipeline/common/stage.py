"""
Base Stage abstraction.

Every pipeline stage (hygiene, knowledge, tasks) subclasses Stage and
implements three methods:

    plan(context)   -> dict   # describe what will be done, without side effects
    run(context)    -> Result # execute
    verify(context) -> bool   # post-run sanity check on outputs

Why the split
-------------
- plan() lets us print a dry-run summary before spending time or tokens.
- verify() is a hook the CLI runs after run() and reports failure early
  (before downstream stages consume broken outputs).

Stages are idempotent. If verify() returns True on entry, run() should
short-circuit and return the existing result — this makes re-runs cheap
and makes the pipeline resumable after a crash.

Phase 0 status: STUB — implemented in Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StageContext:
    """State passed to every stage. Extended per stage as needed."""

    repo_path: Path
    workspace: Path
    config: dict
    run_id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageResult:
    stage: str
    success: bool
    outputs: dict[str, str]
    duration_sec: float
    log_path: Path | None = None
    error: str | None = None


class Stage(ABC):
    name: str

    @abstractmethod
    def plan(self, ctx: StageContext) -> dict: ...

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult: ...

    @abstractmethod
    def verify(self, ctx: StageContext) -> bool: ...
