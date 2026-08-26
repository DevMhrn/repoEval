"""
Base Stage abstraction.

Every pipeline stage (hygiene, knowledge, tasks) subclasses :class:`Stage`
and implements three methods:

- :meth:`Stage.plan`   — describe what will be done, no side effects
- :meth:`Stage.run`    — execute
- :meth:`Stage.verify` — post-run sanity on the produced artifacts

The base class provides :meth:`Stage.execute`, which wraps ``run`` with
manifest-based idempotency. Each stage writes ``.manifests/<stage>.json``
under the workspace after a successful run. The manifest records the hash
of the stage's inputs — repo contents plus the config subset the stage
declared via ``config_keys``. On subsequent invocations:

- Missing or drifted manifest → re-run.
- Matching manifest AND ``verify(ctx)`` still True → cache hit; no work.

That last conjunction matters: if artifacts were deleted between runs the
manifest still exists but verify fails, so we re-run rather than lie
about a cache hit.
"""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        ".idea",
        ".vscode",
    }
)


@dataclass
class StageContext:
    """State handed to every stage.

    ``config`` is a plain dict (typically ``Config.raw``). Sub-stages that
    want typed access pull the relevant sub-table themselves.

    ``extra`` is a bag for stage-to-stage handoff (e.g., knowledge stage
    stashes the loaded graph so tasks stage doesn't reload it).
    """

    repo_path: Path
    workspace: Path
    config: dict[str, Any]
    run_id: str
    extra: dict[str, Any] = field(default_factory=dict)

    def snapshot_hash(self, config_keys: tuple[str, ...]) -> str:
        """Return a stable hash of ``(repo contents, relevant config subset)``.

        Only the config tables named in ``config_keys`` feed the hash, so
        unrelated config edits don't force re-runs of this stage.
        """
        h = hashlib.sha256()
        h.update(b"repo:")
        h.update(_hash_directory(self.repo_path).encode())
        h.update(b"\x1fconfig:")
        subset = {k: self.config.get(k) for k in sorted(config_keys)}
        h.update(
            json.dumps(subset, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        return h.hexdigest()


@dataclass
class StageResult:
    stage: str
    success: bool
    outputs: dict[str, str] = field(default_factory=dict)
    duration_sec: float = 0.0
    log_path: Path | None = None
    error: str | None = None
    manifest_path: Path | None = None
    cache_hit: bool = False


class Stage(ABC):
    """Base class for pipeline stages.

    Subclasses set ``name`` and ``config_keys`` as class attributes and
    implement ``plan``, ``run``, and ``verify``.
    """

    name: str = ""
    config_keys: tuple[str, ...] = ()

    @abstractmethod
    def plan(self, ctx: StageContext) -> dict[str, Any]: ...

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult: ...

    @abstractmethod
    def verify(self, ctx: StageContext) -> bool: ...

    def manifest_path(self, ctx: StageContext) -> Path:
        return ctx.workspace / ".manifests" / f"{self.name}.json"

    def needs_rerun(self, ctx: StageContext) -> bool:
        path = self.manifest_path(ctx)
        if not path.exists():
            return True
        try:
            manifest = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return True
        return manifest.get("input_hash") != ctx.snapshot_hash(self.config_keys)

    def execute(self, ctx: StageContext) -> StageResult:
        if not self.needs_rerun(ctx) and self.verify(ctx):
            manifest = json.loads(self.manifest_path(ctx).read_text())
            return StageResult(
                stage=self.name,
                success=True,
                outputs=manifest.get("outputs", {}),
                duration_sec=manifest.get("duration_sec", 0.0),
                manifest_path=self.manifest_path(ctx),
                cache_hit=True,
            )

        start = _now()
        result = self.run(ctx)
        result.duration_sec = (_now() - start).total_seconds()

        if result.success and not self.verify(ctx):
            result.success = False
            result.error = "verify() returned False after run()"

        if result.success:
            self._write_manifest(ctx, result)
        return result

    def _write_manifest(self, ctx: StageContext, result: StageResult) -> None:
        path = self.manifest_path(ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "stage": self.name,
            "run_id": ctx.run_id,
            "input_hash": ctx.snapshot_hash(self.config_keys),
            "outputs": result.outputs,
            "duration_sec": result.duration_sec,
            "completed_at": _now().isoformat(),
        }
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        result.manifest_path = path


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_directory(root: Path) -> str:
    """Deterministic content hash of a directory tree.

    Ignores VCS metadata, virtualenvs, and common build/cache directories.
    Files are visited in sorted order so results don't depend on
    filesystem iteration order.
    """
    h = hashlib.sha256()
    if not root.exists() or not root.is_dir():
        return h.hexdigest()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIR_NAMES)
        filenames.sort()
        for fname in filenames:
            path = Path(dirpath) / fname
            rel = path.relative_to(root).as_posix()
            h.update(rel.encode("utf-8"))
            h.update(b"\x1f")
            try:
                h.update(hashlib.sha256(path.read_bytes()).digest())
            except OSError:
                h.update(b"unreadable")
            h.update(b"\x1e")
    return h.hexdigest()
