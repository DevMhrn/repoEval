"""
Ecosystem detection and strategy registry.

Any pipeline stage that needs to *do* something ecosystem-specific
(install deps, run tests, choose a docker base image) goes through a
strategy object rather than assuming Python or shelling to pip.

Detection order
---------------
1. Look for known manifest files in repo root (pyproject.toml, setup.py,
   package.json, Cargo.toml, go.mod).
2. Return the first matching strategy.
3. If none match, raise UnsupportedEcosystem.

Extending
---------
To add a language: subclass EcosystemStrategy and register it in REGISTRY.
Phase 1 ships PythonStrategy only. Node/others follow as demand appears.

Phase 0 status: STUB — implemented in Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class UnsupportedEcosystem(Exception):
    pass


class EcosystemStrategy(ABC):
    name: str

    @abstractmethod
    def detect(self, repo_path: Path) -> bool: ...

    @abstractmethod
    def pin_deps(self, repo_path: Path) -> Path: ...

    @abstractmethod
    def install_cmd(self) -> list[str]: ...

    @abstractmethod
    def test_cmd(self) -> list[str]: ...

    @abstractmethod
    def dockerfile_base(self) -> str: ...


def detect(repo_path: Path) -> EcosystemStrategy:
    raise NotImplementedError("Phase 1")
