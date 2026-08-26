"""
Ecosystem detection and strategy registry.

Every pipeline step that does something ecosystem-specific — install
dependencies, run tests, pick a Docker base image, generate a lockfile —
goes through an :class:`EcosystemStrategy`. That's the seam that keeps
the rest of RepoEval repo-agnostic.

Detection
---------
:func:`detect` iterates registered strategy classes in registration order
and returns the first whose ``detect()`` returns True. If no strategy
matches, :class:`UnsupportedEcosystemError` is raised — we never fall back
silently to a default, because a wrong ecosystem choice is a nasty
class of bug to debug later.

Extending
---------
To add a language, subclass :class:`EcosystemStrategy` in a module under
:mod:`pipeline.common.ecosystems` and decorate the class with
:func:`register`. The registration order is the fallback order for
detection; put the most specific strategies first.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class UnsupportedEcosystemError(Exception):
    """Raised when no registered strategy matches the target repo."""


class EcosystemStrategy(ABC):
    """Interface every ecosystem plugin implements.

    Concrete strategies set the ``name`` class attribute and implement
    every abstract method. Methods that need shelling out to tools live
    in the strategy — the caller sites stay ecosystem-agnostic.
    """

    name: str = ""

    @abstractmethod
    def detect(self, repo_path: Path) -> bool: ...

    @abstractmethod
    def pin_deps(self, repo_path: Path, workdir: Path) -> Path:
        """Produce a fully-pinned lockfile. Returns the lockfile path."""

    @abstractmethod
    def install_cmd(self) -> list[str]:
        """Command that installs pinned deps inside the container."""

    @abstractmethod
    def test_cmd(self, test_selection: list[str] | None = None) -> list[str]:
        """Command to run the test suite; optionally scoped to selection."""

    @abstractmethod
    def dockerfile_base(self) -> str:
        """Default base image for the ecosystem (config may override)."""

    @abstractmethod
    def discover_test_paths(self, repo_path: Path) -> list[Path]:
        """Return sorted absolute paths to test directories/files."""


_REGISTRY: list[type[EcosystemStrategy]] = []


def register(cls: type[EcosystemStrategy]) -> type[EcosystemStrategy]:
    """Class decorator that adds a strategy to the detection registry."""
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def _load_builtin_strategies() -> None:
    # Import for side-effect: modules use @register at import time.
    from .ecosystems import python  # noqa: F401


def detect(repo_path: Path) -> EcosystemStrategy:
    _load_builtin_strategies()
    for cls in _REGISTRY:
        strategy = cls()
        if strategy.detect(repo_path):
            return strategy
    raise UnsupportedEcosystemError(
        f"no ecosystem strategy matched {repo_path}"
    )
