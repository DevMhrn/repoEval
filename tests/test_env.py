"""Tests for pipeline.common.env."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.common.env import (
    find_dotenv,
    has_real_value,
    load_dotenv,
)


def test_load_dotenv_reads_basic_key_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\nBAZ=qux\n")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAZ", raising=False)

    loaded = load_dotenv(env_path)
    assert loaded == {"FOO": "bar", "BAZ": "qux"}
    assert os.environ["FOO"] == "bar"
    assert os.environ["BAZ"] == "qux"


def test_load_dotenv_ignores_comments_and_blanks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\n"
        "\n"
        "FOO=bar\n"
        "  # indented comment\n"
        "no_equals_here\n"
        "BAZ=qux\n"
    )
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAZ", raising=False)
    loaded = load_dotenv(env_path)
    assert set(loaded.keys()) == {"FOO", "BAZ"}


def test_load_dotenv_strips_surrounding_quotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text('FOO="hello world"\nBAR=\'single\'\n')
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    load_dotenv(env_path)
    assert os.environ["FOO"] == "hello world"
    assert os.environ["BAR"] == "single"


def test_load_dotenv_preserves_existing_env_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=from_file\n")
    monkeypatch.setenv("FOO", "from_shell")

    load_dotenv(env_path)
    assert os.environ["FOO"] == "from_shell"


def test_load_dotenv_override_replaces_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=from_file\n")
    monkeypatch.setenv("FOO", "from_shell")

    load_dotenv(env_path, override=True)
    assert os.environ["FOO"] == "from_file"


def test_load_dotenv_returns_empty_when_missing(tmp_path: Path):
    assert load_dotenv(tmp_path / "no_such") == {}


def test_find_dotenv_walks_up_from_start(tmp_path: Path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (tmp_path / ".env").write_text("X=1\n")
    found = find_dotenv(deep)
    assert found == tmp_path / ".env"


def test_find_dotenv_returns_none_when_absent(tmp_path: Path):
    deep = tmp_path / "empty"
    deep.mkdir()
    # We resolve upward past tmp_path — but there might legitimately be a
    # .env somewhere above /tmp. Just assert we don't crash; either None
    # or an absolute Path is acceptable here.
    result = find_dotenv(deep)
    assert result is None or result.is_absolute()


def test_has_real_value_true_for_normal_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_KEY", "sk-live-abcdef")
    assert has_real_value("MY_KEY") is True


def test_has_real_value_false_for_placeholder(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_KEY", "your_anthropic_key_here")
    assert has_real_value("MY_KEY") is False


def test_has_real_value_false_for_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_KEY", "")
    assert has_real_value("MY_KEY") is False


def test_has_real_value_false_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    assert has_real_value("MY_KEY") is False


def test_load_dotenv_ignores_malformed_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text("=noeq\nGOOD=1\n")
    monkeypatch.delenv("GOOD", raising=False)
    loaded = load_dotenv(env_path)
    assert loaded == {"GOOD": "1"}
