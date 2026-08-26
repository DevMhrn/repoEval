"""
Config loader.

Reads repoeval.toml at the workspace root and merges in optional
repoeval.local.toml overrides. Returns a typed Config object used by every
stage.

Contracts
---------
- If repoeval.toml is missing, we fail loudly. Never silently fall back to
  hardcoded defaults — that would hide misconfiguration.
- repoeval.local.toml is optional and never checked in; used for per-machine
  overrides (API keys, workspace paths).

Phase 0 status: STUB — real loader lands in Phase 1 alongside the first stage
that consumes a config value.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Placeholder — expanded when the first stage needs typed access."""

    config_path: Path
    raw: dict


def load(path: Path) -> Config:
    raise NotImplementedError("Phase 1")
