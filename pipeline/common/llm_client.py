"""
LLM client with record/replay.

Every LLM call in RepoEval goes through this one client. Two reasons:

1. **Determinism.** In ``replay`` mode the client reads
   ``(prompt -> response)`` pairs from a fixture cache and never touches
   the network. Same input → same output, always. Reviewers reproducing
   results get bit-identical pipeline output for $0.
2. **Auditability.** In ``record`` mode every call is written to the
   fixtures cache and appended to a session JSONL under transcripts/.
   The transcripts/ deliverable is populated automatically.

Fixture key is a 16-char sha256 prefix over ``(model, temperature,
system, prompt)`` — the four inputs that affect the response. Purpose
strings and other metadata are excluded so rewording a purpose tag
doesn't invalidate the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Mode = Literal["record", "replay"]


class MissingFixtureError(Exception):
    """Raised in replay mode when the requested fixture doesn't exist."""


class LLMClientError(Exception):
    """Raised for unrecoverable client-side problems."""


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    fixture_key: str
    cached: bool


@dataclass
class _FixtureRecord:
    key: str
    model: str
    temperature: float
    system: str | None
    prompt: str
    response_text: str
    input_tokens: int
    output_tokens: int
    saved_at: str


def fixture_key(
    model: str,
    temperature: float,
    system: str | None,
    prompt: str,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "system": system,
            "prompt": prompt,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class LLMClient:
    def __init__(
        self,
        *,
        mode: Mode,
        model: str,
        fixtures_dir: Path,
        transcripts_dir: Path | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ):
        if mode not in ("record", "replay"):
            raise LLMClientError(f"unknown mode: {mode}")
        self.mode = mode
        self.model = model
        self.fixtures_dir = fixtures_dir
        self.transcripts_dir = transcripts_dir
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._session_id = _session_id()

    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
    ) -> LLMResponse:
        key = fixture_key(self.model, self.temperature, system, prompt)
        fixture_path = self.fixtures_dir / f"{key}.json"

        if fixture_path.exists():
            record = _load_fixture(fixture_path)
            return LLMResponse(
                text=record.response_text,
                model=record.model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                fixture_key=key,
                cached=True,
            )

        if self.mode == "replay":
            raise MissingFixtureError(
                f"no fixture for key {key} (purpose={purpose})"
            )

        response = self._call_api(prompt, system)
        record = _FixtureRecord(
            key=key,
            model=self.model,
            temperature=self.temperature,
            system=system,
            prompt=prompt,
            response_text=response["text"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            saved_at=_now().isoformat(),
        )
        _write_fixture(fixture_path, record)
        self._append_transcript(purpose, key, prompt, response, system)
        return LLMResponse(
            text=response["text"],
            model=self.model,
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            fixture_key=key,
            cached=False,
        )

    def _call_api(self, prompt: str, system: str | None) -> dict[str, Any]:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMClientError("anthropic SDK not installed") from e
        if not self._api_key:
            raise LLMClientError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=self._api_key)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Note: temperature was removed from the Anthropic API in SDK 1.0
        # (Claude 5+). We keep ``self.temperature`` because it still feeds
        # the fixture cache key — flipping it invalidates cached responses
        # even though the API itself no longer accepts the parameter.
        if system:
            kwargs["system"] = system
        msg = client.messages.create(**kwargs)
        text = "".join(
            block.text
            for block in msg.content
            if getattr(block, "type", "") == "text"
        )
        return {
            "text": text,
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }

    def _append_transcript(
        self,
        purpose: str,
        key: str,
        prompt: str,
        response: dict[str, Any],
        system: str | None,
    ) -> None:
        if not self.transcripts_dir:
            return
        sink = self.transcripts_dir / f"session_{self._session_id}.jsonl"
        sink.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _now().isoformat(),
            "session_id": self._session_id,
            "purpose": purpose,
            "fixture_key": key,
            "model": self.model,
            "temperature": self.temperature,
            "system": system,
            "prompt": prompt,
            "response": response["text"],
            "input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
        }
        with sink.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_fixture(path: Path) -> _FixtureRecord:
    data = json.loads(path.read_text())
    return _FixtureRecord(**data)


def _write_fixture(path: Path, record: _FixtureRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(asdict(record), indent=2, ensure_ascii=False, sort_keys=True)
    )
    tmp.replace(path)


def _now() -> datetime:
    return datetime.now(UTC)


def _session_id() -> str:
    return _now().strftime("%Y%m%d_%H%M%S")
