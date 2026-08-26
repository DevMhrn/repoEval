"""Tests for pipeline.common.llm_client and the prompt loader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.common.llm_client import (
    LLMClient,
    LLMClientError,
    MissingFixtureError,
    fixture_key,
)
from pipeline.common.prompts.loader import (
    PromptNotFoundError,
    load_prompt,
)


def test_fixture_key_is_stable():
    a = fixture_key("m", 0.0, None, "hi")
    b = fixture_key("m", 0.0, None, "hi")
    assert a == b
    assert len(a) == 16


def test_fixture_key_changes_with_any_input():
    base = fixture_key("m", 0.0, None, "hi")
    assert fixture_key("m2", 0.0, None, "hi") != base
    assert fixture_key("m", 0.1, None, "hi") != base
    assert fixture_key("m", 0.0, "system!", "hi") != base
    assert fixture_key("m", 0.0, None, "hey") != base


def test_replay_reads_prewritten_fixture(tmp_path: Path):
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    key = fixture_key("m", 0.0, None, "hi")
    (fixtures / f"{key}.json").write_text(
        json.dumps(
            {
                "key": key,
                "model": "m",
                "temperature": 0.0,
                "system": None,
                "prompt": "hi",
                "response_text": "hello",
                "input_tokens": 3,
                "output_tokens": 2,
                "saved_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    client = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    r = client.complete("hi", purpose="test")
    assert r.text == "hello"
    assert r.cached is True
    assert r.input_tokens == 3
    assert r.fixture_key == key


def test_replay_missing_fixture_raises(tmp_path: Path):
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    client = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    with pytest.raises(MissingFixtureError, match="no fixture"):
        client.complete("nope", purpose="test")


def _fake_anthropic(text: str = "the answer", in_tok: int = 5, out_tok: int = 7):
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(type="text", text=text)]
    fake_msg.usage.input_tokens = in_tok
    fake_msg.usage.output_tokens = out_tok

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    return fake_anthropic, fake_client


def test_record_writes_fixture_and_transcript(tmp_path: Path):
    fixtures = tmp_path / "fx"
    transcripts = tmp_path / "tx"
    fake_anthropic, _ = _fake_anthropic()

    client = LLMClient(
        mode="record",
        model="m",
        fixtures_dir=fixtures,
        transcripts_dir=transcripts,
        api_key="fake",
    )

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        r = client.complete("what?", purpose="unit-test")

    assert r.text == "the answer"
    assert r.cached is False
    assert r.input_tokens == 5
    assert r.output_tokens == 7

    fixture_files = list(fixtures.glob("*.json"))
    assert len(fixture_files) == 1
    data = json.loads(fixture_files[0].read_text())
    assert data["response_text"] == "the answer"
    assert data["prompt"] == "what?"

    transcript_files = list(transcripts.glob("session_*.jsonl"))
    assert len(transcript_files) == 1
    entries = [
        json.loads(line)
        for line in transcript_files[0].read_text().splitlines()
    ]
    assert entries[0]["purpose"] == "unit-test"
    assert entries[0]["prompt"] == "what?"
    assert entries[0]["response"] == "the answer"


def test_record_second_call_serves_from_cache_no_api(tmp_path: Path):
    fixtures = tmp_path / "fx"
    fake_anthropic, fake_client = _fake_anthropic(text="cached-hit")

    client = LLMClient(
        mode="record",
        model="m",
        fixtures_dir=fixtures,
        api_key="fake",
    )

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        first = client.complete("x", purpose="p1")
        second = client.complete("x", purpose="p2")

    assert fake_client.messages.create.call_count == 1
    assert first.cached is False
    assert second.cached is True
    assert first.text == second.text == "cached-hit"


def test_record_passes_system_prompt(tmp_path: Path):
    fake_anthropic, fake_client = _fake_anthropic()
    client = LLMClient(
        mode="record",
        model="m",
        fixtures_dir=tmp_path,
        api_key="fake",
    )
    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        client.complete("hi", purpose="p", system="you are a helper")
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "you are a helper"


def test_unknown_mode_raises(tmp_path: Path):
    with pytest.raises(LLMClientError, match="unknown mode"):
        LLMClient(mode="oops", model="m", fixtures_dir=tmp_path)  # type: ignore[arg-type]


def test_record_without_api_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = LLMClient(mode="record", model="m", fixtures_dir=tmp_path)
    fake_anthropic, _ = _fake_anthropic()
    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        with pytest.raises(LLMClientError, match="API_KEY"):
            client.complete("hi", purpose="test")


def test_load_prompt_basic(tmp_path: Path):
    (tmp_path / "greet.md").write_text("Hello {name}!\n")
    tpl = load_prompt("greet", prompts_dir=tmp_path)
    assert tpl.name == "greet"
    assert tpl.render(name="world") == "Hello world!\n"


def test_load_prompt_with_frontmatter(tmp_path: Path):
    (tmp_path / "x.md").write_text(
        "---\nname: x\npurpose: demo\n---\nBody {slot}.\n"
    )
    tpl = load_prompt("x", prompts_dir=tmp_path)
    assert tpl.metadata["purpose"] == "demo"
    assert tpl.render(slot="here") == "Body here.\n"


def test_load_prompt_missing_raises(tmp_path: Path):
    with pytest.raises(PromptNotFoundError):
        load_prompt("nope", prompts_dir=tmp_path)


def test_render_leaves_unknown_placeholders_literal(tmp_path: Path):
    (tmp_path / "p.md").write_text("Known: {known} Unknown: {other}\n")
    tpl = load_prompt("p", prompts_dir=tmp_path)
    rendered = tpl.render(known="here")
    assert "Known: here" in rendered
    assert "{other}" in rendered
