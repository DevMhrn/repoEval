"""
LLM enrichment.

For each module, ask the LLM for a 1-2 sentence summary of what it does.
Cache aggressively — a module summary only changes when the module changes.

We keep LLM contributions to the knowledge layer minimal and clearly
labeled ("source": "llm") so downstream consumers can weight them
appropriately vs. statically-derived facts.

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path

from ..common.llm_client import LLMClient


def enrich_with_llm(graph: dict, repo_path: Path, llm: LLMClient) -> dict:
    raise NotImplementedError("Phase 2")
