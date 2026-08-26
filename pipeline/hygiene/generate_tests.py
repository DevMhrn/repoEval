"""
Generate unit tests for low-coverage modules.

Anti-coverage-theater guardrails
--------------------------------
- Each generated test must contain at least one assertion on a return value
  or observable side effect. Tests that merely call a function pass syntax
  checks but are rejected.
- We inject a small deliberate bug into each covered function and re-run the
  generated tests. A generated test that still passes with the bug present is
  discarded (it does not actually verify behavior).

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy
from ..common.llm_client import LLMClient


def generate_tests(
    repo_path: Path,
    ecosystem: EcosystemStrategy,
    llm: LLMClient,
    coverage_gaps: list[str],
) -> list[Path]:
    raise NotImplementedError("Phase 1")
