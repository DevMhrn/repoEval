"""Tests for pipeline.common.validator.harness."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.validator.artifact import TaskArtifact
from pipeline.common.validator.harness import validate_task


def _shape(tmp_path: Path) -> TaskArtifact:
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    (art.verifier_dir / "Dockerfile").write_text("FROM alpine\n")
    (art.solution_dir / "src.py").write_text("def x(): return 1\n")
    (art.input_dir / "src.py").write_text("def x(): return 0\n")
    return art


def _fake_builder(df, ctx, tag):
    return f"sha:{tag}"


def _scripted_runner(script: dict):
    """Runner that reacts to source mount to decide reward / stdout.

    ``script`` shape::
        {
            "/repo": <depends on mount source>
        }

    Actually simpler: dispatch by ``mount source folder name``.
    """
    def run(image, cmd, *, mounts=None, working_dir=None, **kwargs):
        source = "unknown"
        logs = None
        for host, target in mounts.items():
            if target == "/repo":
                source = host.name  # "input" or "solution"
            elif target == "/logs":
                logs = host
        response = script.get(source, {})
        reward = response.get("reward")
        stdout = response.get("stdout", "")
        if reward is not None and logs is not None:
            (logs / "verifier").mkdir(parents=True, exist_ok=True)
            (logs / "verifier" / "reward.txt").write_text(reward)
        # Emit full report if command references full_report path.
        if isinstance(cmd, list) and any("full_report" in c for c in cmd):
            (logs / "full_report.json").write_text(
                json.dumps(response.get("full_report", {"tests": []}))
            )
        return RunResult(
            exit_code=response.get("exit_code", 0),
            stdout=stdout,
            stderr="",
            duration_sec=0.1,
        )
    return run


def test_harness_passes_when_all_checks_green(tmp_path: Path):
    art = _shape(tmp_path)
    runner = _scripted_runner(
        {
            "solution": {"reward": "1", "stdout": "===== 1 passed in 0.01s =====\n"},
            "input": {
                "reward": "0",
                "stdout": (
                    "FAILED tests/test_x.py::test_y - AssertionError\n"
                    "===== 1 failed in 0.01s =====\n"
                ),
            },
        }
    )
    report = validate_task(
        art.task_folder,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    assert report.verdict == "pass"
    verdicts = {c["check"]: c["verdict"] for c in report.checks}
    assert verdicts["pass_after"] == "pass"
    assert verdicts["fail_before"] == "pass"
    assert verdicts["determinism"] == "pass"


def test_harness_fails_when_pass_after_fails(tmp_path: Path):
    art = _shape(tmp_path)
    runner = _scripted_runner(
        {
            "solution": {"reward": "0"},
            "input": {
                "reward": "0",
                "stdout": "FAILED - AssertionError\n===== 1 failed =====\n",
            },
        }
    )
    report = validate_task(
        art.task_folder,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    assert report.verdict == "fail"


def test_harness_error_wins_over_fail(tmp_path: Path):
    art = _shape(tmp_path)
    runner = _scripted_runner(
        {
            "solution": {"reward": "1", "stdout": "===== 1 passed in 0.01s =====\n"},
            "input": {"reward": "0", "stdout": "ImportError: nope\n"},
        }
    )
    report = validate_task(
        art.task_folder,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    assert report.verdict == "error"


def test_harness_writes_evidence_report(tmp_path: Path):
    art = _shape(tmp_path)
    runner = _scripted_runner(
        {
            "solution": {"reward": "1"},
            "input": {"reward": "0", "stdout": "FAILED - AssertionError\n"},
        }
    )
    validate_task(
        art.task_folder,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    report_path = art.evidence_report_path
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["verdict"] in {"pass", "fail", "error"}
    assert isinstance(data["checks"], list)
    assert data["determinism_repeats"] == 2


def test_harness_includes_no_collateral_when_baseline_provided(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"tests": [{"nodeid": "tests/test_a.py::test_x", "outcome": "passed"}]}
        )
    )

    runner = _scripted_runner(
        {
            "solution": {
                "reward": "1",
                "stdout": "===== 1 passed in 0.01s =====\n",
                "full_report": {
                    "tests": [
                        {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"}
                    ]
                },
            },
            "input": {
                "reward": "0",
                "stdout": "FAILED - AssertionError\n===== 1 failed in 0.01s =====\n",
            },
        }
    )
    report = validate_task(
        art.task_folder,
        baseline_report=baseline,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    check_names = [c["check"] for c in report.checks]
    assert "no_collateral" in check_names


def test_harness_skips_determinism_on_pass_after_error(tmp_path: Path):
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    # no Dockerfile -> pass_after errors
    runner = _scripted_runner({"solution": {}, "input": {}})
    report = validate_task(
        art.task_folder,
        determinism_repeats=2,
        runner=runner,
        builder=_fake_builder,
    )
    check_names = [c["check"] for c in report.checks]
    assert "determinism" not in check_names
    assert report.verdict == "error"
