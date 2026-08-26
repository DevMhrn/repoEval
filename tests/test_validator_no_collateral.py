"""Tests for pipeline.common.validator.checks.no_collateral."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.validator.artifact import TaskArtifact
from pipeline.common.validator.checks import Verdict, no_collateral


def _shape(tmp_path: Path) -> TaskArtifact:
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    (art.verifier_dir / "Dockerfile").write_text("FROM alpine\n")
    (art.solution_dir / "src.py").write_text("def x(): return 1\n")
    return art


def _baseline(tmp_path: Path, tests: list[dict]) -> Path:
    path = tmp_path / "baseline_report.json"
    path.write_text(json.dumps({"tests": tests}))
    return path


def _report_runner(report: dict):
    def run(image, cmd, *, mounts=None, **kwargs):
        logs = None
        for host, target in mounts.items():
            if target == "/logs":
                logs = host
                break
        assert logs is not None
        (logs / "full_report.json").write_text(json.dumps(report))
        return RunResult(exit_code=0, stdout="", stderr="", duration_sec=0.1)
    return run


def _fake_builder(df, ctx, tag):
    return f"sha:{tag}"


def test_pass_when_all_baseline_tests_still_pass(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [
            {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
            {"nodeid": "tests/test_a.py::test_y", "outcome": "passed"},
        ],
    )
    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=_report_runner(
            {
                "tests": [
                    {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
                    {"nodeid": "tests/test_a.py::test_y", "outcome": "passed"},
                ]
            }
        ),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.PASS
    assert result.metadata["regressions"] == 0


def test_fail_when_previously_passing_test_now_fails(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [
            {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
            {"nodeid": "tests/test_a.py::test_y", "outcome": "passed"},
        ],
    )
    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=_report_runner(
            {
                "tests": [
                    {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
                    {"nodeid": "tests/test_a.py::test_y", "outcome": "failed"},
                ]
            }
        ),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.FAIL
    assert result.metadata["regressions"] == 1
    data = json.loads(result.evidence_path.read_text())
    assert data["regressions"][0]["nodeid"] == "tests/test_a.py::test_y"


def test_pass_when_baseline_tests_originally_failed_still_fail(tmp_path: Path):
    # We only care about tests that passed at baseline.
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [
            {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
            {"nodeid": "tests/test_flake.py::test_z", "outcome": "failed"},
        ],
    )
    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=_report_runner(
            {
                "tests": [
                    {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
                    {"nodeid": "tests/test_flake.py::test_z", "outcome": "failed"},
                ]
            }
        ),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.PASS


def test_pass_when_new_passing_tests_added(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [{"nodeid": "tests/test_a.py::test_x", "outcome": "passed"}],
    )
    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=_report_runner(
            {
                "tests": [
                    {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
                    {"nodeid": "tests/test_new.py::test_added", "outcome": "passed"},
                ]
            }
        ),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.PASS


def test_error_when_baseline_report_missing(tmp_path: Path):
    result = no_collateral(
        _shape(tmp_path),
        baseline_report=tmp_path / "nowhere.json",
        runner=_report_runner({"tests": []}),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.ERROR
    assert "not found" in result.reason


def test_error_when_container_produces_no_report(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [{"nodeid": "tests/test_a.py::test_x", "outcome": "passed"}],
    )

    def no_write_runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(exit_code=2, stdout="crash", stderr="", duration_sec=0.1)

    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=no_write_runner,
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.ERROR
    assert "did not emit" in result.reason


def test_missing_current_test_is_recorded_not_regression(tmp_path: Path):
    art = _shape(tmp_path)
    baseline = _baseline(
        tmp_path,
        [{"nodeid": "tests/test_a.py::test_x", "outcome": "passed"}],
    )
    result = no_collateral(
        art,
        baseline_report=baseline,
        runner=_report_runner({"tests": []}),
        builder=_fake_builder,
    )
    # A missing test is recorded but not counted as a regression here.
    assert result.verdict == Verdict.PASS
    data = json.loads(result.evidence_path.read_text())
    assert data["missing_from_current"] == ["tests/test_a.py::test_x"]
