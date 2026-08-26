"""
LLM client with record/replay semantics.

Every LLM interaction in RepoEval goes through this one client. Two reasons:

1. Determinism. In replay mode the client reads (prompt -> response) pairs
   from fixtures/ and never touches the network. Same input -> same output,
   always. Reviewers reproducing results get bit-identical pipeline output.

2. Auditability. In record mode every call is written to the fixtures cache
   AND to a session JSONL under transcripts/. The transcripts/ deliverable
   is populated automatically.

Fixture key = sha256(prompt + model + temperature). Collisions are checked.

Phase 0 status: STUB — implemented in Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    fixture_key: str


class LLMClient:
    def __init__(
        self,
        mode: Literal["record", "replay"],
        model: str,
        fixtures_dir: Path,
        transcripts_dir: Path | None = None,
        temperature: float = 0.0,
    ):
        self.mode = mode
        self.model = model
        self.fixtures_dir = fixtures_dir
        self.transcripts_dir = transcripts_dir
        self.temperature = temperature

    def complete(self, prompt: str, purpose: str) -> LLMResponse:
        """
        purpose is a human-readable slug (e.g. "instruction_writer") used
        only for transcripts/ so a human reader can find the relevant call.
        """
        raise NotImplementedError("Phase 1")
