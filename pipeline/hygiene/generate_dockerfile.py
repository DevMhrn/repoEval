"""
Generate the Dockerfile.

Rules
-----
- Base image chosen by ecosystem strategy.
- Install exact-pinned deps via the lockfile (not the manifest).
- Install test runner and any tools the verifier needs.
- ENTRYPOINT is a no-op; the test command is invoked explicitly by run.sh so
  the same image can be used for interactive debugging.

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy


def generate_dockerfile(repo_path: Path, ecosystem: EcosystemStrategy) -> Path:
    raise NotImplementedError("Phase 1")
