"""
Net-new feature mining.

Proposes small capabilities the repo lacks, then authors tests defining the
expected behavior. Proposals come from the LLM but are gated:
    - Must be scoped to a single module.
    - Must not depend on external services.
    - Must be implementable in < ~200 LOC (heuristic).

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ...common.llm_client import LLMClient


def mine_net_new(
    repo_path: Path,
    graph: dict,
    llm: LLMClient,
    limit: int,
) -> list[dict]:
    raise NotImplementedError("Phase 3")
