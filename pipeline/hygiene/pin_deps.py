"""
Pin dependencies.

Delegates to the ecosystem strategy (e.g., PythonStrategy uses uv/pip-tools to
compile a lockfile). We never call the tool directly from here — that keeps
this file repo-agnostic.

Success criteria
----------------
- A lockfile exists in the repo.
- A fresh clone + install using the lockfile produces the same resolved
  versions (verified by re-running the install and diffing).

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy


def pin_deps(repo_path: Path, ecosystem: EcosystemStrategy) -> Path:
    raise NotImplementedError("Phase 1")
