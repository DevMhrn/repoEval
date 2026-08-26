"""Tests for pipeline.common.logging."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from pipeline.common.logging import get_logger, make_run_id


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _capture_console(buf: StringIO) -> Console:
    return Console(file=buf, force_terminal=False, width=200)


def test_make_run_id_is_deterministic_with_entropy_source():
    ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    assert make_run_id("hygiene", ts, entropy_source="abcd") == "hygiene-20260115-103000-abcd"


def test_make_run_id_random_suffix_is_four_hex_chars():
    ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    rid1 = make_run_id("hygiene", ts)
    rid2 = make_run_id("hygiene", ts)
    assert rid1 != rid2
    for rid in (rid1, rid2):
        suffix = rid.rsplit("-", 1)[1]
        assert len(suffix) == 4
        int(suffix, 16)


def test_logger_writes_events_to_jsonl_sink(tmp_path: Path):
    buf = StringIO()
    log = get_logger("hygiene", "hygiene-run", tmp_path, console=_capture_console(buf))
    log.event("stage.start", target="glom")
    log.step_start("pin_deps", tool="uv")
    log.step_end("pin_deps", ok=True, duration=1.23)
    log.close()

    events = _read_jsonl(tmp_path / "hygiene" / "hygiene-run.jsonl")
    assert len(events) == 3

    for rec in events:
        assert rec["stage"] == "hygiene"
        assert rec["run_id"] == "hygiene-run"
        assert "ts" in rec
        assert "event" in rec
        assert "data" in rec

    assert events[0]["event"] == "stage.start"
    assert events[0]["data"]["target"] == "glom"
    assert events[1]["event"] == "step.start"
    assert events[1]["data"]["step"] == "pin_deps"
    assert events[1]["data"]["tool"] == "uv"
    assert events[2]["event"] == "step.end"
    assert events[2]["data"]["ok"] is True
    assert events[2]["data"]["duration"] == 1.23


def test_logger_error_records_message(tmp_path: Path):
    buf = StringIO()
    log = get_logger("tasks", "tasks-x", tmp_path, console=_capture_console(buf))
    log.error("verifier crashed", exit_code=137)
    log.close()

    events = _read_jsonl(tmp_path / "tasks" / "tasks-x.jsonl")
    assert events[0]["event"] == "error"
    assert events[0]["data"]["message"] == "verifier crashed"
    assert events[0]["data"]["exit_code"] == 137


def test_logger_mirrors_summary_to_console(tmp_path: Path):
    buf = StringIO()
    log = get_logger("knowledge", "k1", tmp_path, console=_capture_console(buf))
    log.event("hello", step="warmup")
    log.close()
    out = buf.getvalue()
    assert "knowledge" in out
    assert "hello" in out
    assert "warmup" in out


def test_logger_context_manager_closes_sink(tmp_path: Path):
    buf = StringIO()
    with get_logger("hygiene", "cm-run", tmp_path, console=_capture_console(buf)) as log:
        log.event("start")
    events = _read_jsonl(tmp_path / "hygiene" / "cm-run.jsonl")
    assert len(events) == 1


def test_logger_emit_after_close_raises(tmp_path: Path):
    buf = StringIO()
    log = get_logger("hygiene", "r", tmp_path, console=_capture_console(buf))
    log.close()
    with pytest.raises(RuntimeError, match="closed"):
        log.event("late")


def test_step_end_fail_records_ok_false(tmp_path: Path):
    buf = StringIO()
    log = get_logger("hygiene", "r", tmp_path, console=_capture_console(buf))
    log.step_end("build", ok=False, reason="docker daemon down")
    log.close()
    ev = _read_jsonl(tmp_path / "hygiene" / "r.jsonl")[0]
    assert ev["data"]["ok"] is False
    assert ev["data"]["reason"] == "docker daemon down"


def test_sink_directory_is_created_lazily(tmp_path: Path):
    buf = StringIO()
    target_dir = tmp_path / "does" / "not" / "exist"
    assert not target_dir.exists()
    log = get_logger("hygiene", "r", target_dir, console=_capture_console(buf))
    log.event("first")
    log.close()
    assert (target_dir / "hygiene" / "r.jsonl").exists()


def test_multiple_events_share_run_id_and_stage(tmp_path: Path):
    buf = StringIO()
    log = get_logger("tasks", "shared-id", tmp_path, console=_capture_console(buf))
    for i in range(5):
        log.event(f"e{i}")
    log.close()

    events = _read_jsonl(tmp_path / "tasks" / "shared-id.jsonl")
    assert len(events) == 5
    assert {e["run_id"] for e in events} == {"shared-id"}
    assert {e["stage"] for e in events} == {"tasks"}
