"""Tests for pipeline.common.validator.checks.fail_before and pytest_output."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.validator.artifact import TaskArtifact
from pipeline.common.validator.checks import Verdict, fail_before
from pipeline.common.validator.pytest_output import parse_pytest_output


def _shape(tmp_path: Path) -> TaskArtifact:
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    (art.verifier_dir / "Dockerfile").write_text("FROM alpine\n")
    (art.verifier_dir / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (art.input_dir / "src.py").write_text("def x(): return 0\n")
    return art


def _runner(
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 1,
    reward: str | None = "0",
):
    def run(image, cmd, *, mounts=None, **kwargs):
        assert mounts is not None
        logs_dir = None
        for host, target in mounts.items():
            if target == "/logs":
                logs_dir = host
                break
        assert logs_dir is not None
        if reward is not None:
            (logs_dir / "verifier").mkdir(parents=True, exist_ok=True)
            (logs_dir / "verifier" / "reward.txt").write_text(reward)
        return RunResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_sec=0.1,
        )
    return run


def _builder(df, ctx, tag):
    return f"sha:{tag}"


def test_fail_before_passes_on_real_assertion_failure(tmp_path: Path):
    stdout = (
        "FAILED tests/test_x.py::test_y - AssertionError: assert 0 == 1\n"
        "======= 1 failed in 0.01s =======\n"
    )
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=1, reward="0"),
        builder=_builder,
    )
    assert result.verdict == Verdict.PASS
    assert "as expected" in result.reason


def test_fail_before_errors_on_import_error(tmp_path: Path):
    stdout = (
        "ERROR tests/test_x.py - ImportError: no module named 'missing'\n"
        "======= 1 error in 0.01s =======\n"
    )
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=2, reward="0"),
        builder=_builder,
    )
    assert result.verdict == Verdict.ERROR
    assert "collection" in result.reason


def test_fail_before_errors_on_syntax_error(tmp_path: Path):
    stdout = "SyntaxError: invalid syntax\n"
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=2, reward="0"),
        builder=_builder,
    )
    assert result.verdict == Verdict.ERROR


def test_fail_before_fails_when_verifier_actually_passed_on_input(tmp_path: Path):
    stdout = "======= 3 passed in 0.02s =======\n"
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=0, reward="1"),
        builder=_builder,
    )
    assert result.verdict == Verdict.FAIL
    assert "passed on input" in result.reason


def test_fail_before_error_when_no_assertion_signal(tmp_path: Path):
    stdout = "verifier crashed with 137\n"
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=1, reward="0"),
        builder=_builder,
    )
    assert result.verdict == Verdict.ERROR


def test_fail_before_relaxed_mode_accepts_any_failure(tmp_path: Path):
    stdout = "some non-standard failure output\n"
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, exit_code=1, reward="0"),
        builder=_builder,
        require_assertion_failure=False,
    )
    assert result.verdict == Verdict.PASS


def test_fail_before_writes_evidence(tmp_path: Path):
    stdout = (
        "FAILED tests/x.py::t - AssertionError: nope\n"
        "======= 1 failed in 0.01s =======\n"
    )
    result = fail_before(
        _shape(tmp_path),
        runner=_runner(stdout=stdout, reward="0"),
        builder=_builder,
    )
    data = json.loads(result.evidence_path.read_text())
    assert data["verdict"] == "pass"
    assert data["has_assertion_failure"] is True
    assert data["has_collection_error"] is False
    assert data["counts"]["failed"] == 1


def test_parse_summary_counts():
    text = "======= 2 passed, 1 failed, 1 skipped in 0.05s =======\n"
    outcome = parse_pytest_output(text)
    assert outcome.passed == 2
    assert outcome.failed == 1
    assert outcome.skipped == 1


def test_parse_detects_assertion_failure():
    outcome = parse_pytest_output("AssertionError: value mismatch\n")
    assert outcome.has_assertion_failure is True


def test_parse_detects_import_error():
    outcome = parse_pytest_output("ImportError: no such\n")
    assert outcome.has_collection_error is True


def test_parse_recognises_failed_and_error_lines():
    text = (
        "FAILED tests/a.py::test_one - AssertionError\n"
        "ERROR tests/b.py - ImportError\n"
    )
    outcome = parse_pytest_output(text)
    assert any("FAILED" in line for line in outcome.failure_lines)
    assert any("ERROR" in line for line in outcome.failure_lines)


def test_parse_empty_output_is_neutral():
    outcome = parse_pytest_output("")
    assert outcome.has_assertion_failure is False
    assert outcome.has_collection_error is False
    assert outcome.passed == 0
