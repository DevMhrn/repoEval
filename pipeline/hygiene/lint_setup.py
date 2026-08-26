"""
Introduce linter and formatter, apply, commit changes.

For Python: ruff + black with sensible defaults. Auto-fix, then verify the
lint pass is clean (exit 0).

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy


def setup_lint(repo_path: Path, ecosystem: EcosystemStrategy) -> None:
    raise NotImplementedError("Phase 1")
