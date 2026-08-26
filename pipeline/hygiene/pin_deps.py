"""
Pin dependencies delegator.

Detects the ecosystem for ``repo_path`` and asks that strategy to
produce a lockfile. Everything ecosystem-specific lives in the
strategy; this module stays language-neutral.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy, detect


def pin_deps(
    repo_path: Path,
    workdir: Path,
    *,
    strategy: EcosystemStrategy | None = None,
) -> Path:
    strategy = strategy or detect(repo_path)
    return strategy.pin_deps(repo_path, workdir)
