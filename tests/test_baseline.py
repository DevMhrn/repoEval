"""Tests for pipeline.hygiene.baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.common.docker_utils import RunResult
from pipeline.hygiene.baseline import (
    BaselineReport,
    parse_report,
    run_baseline,
    write_report,
)

_MINIMAL_REPORT = {
    "duration": 0.42,
    "tests": [
        {"nodeid": "tests/test_a.py::test_x", "outcome": "passed",
         "call": {"duration": 0.1}},
        {"nodeid": "tests/test_a.py::test_y", "outcome": "failed",
         "call": {"duration": 0.05}},
        {"nodeid": "tests/test_b.py::test_z", "outcome": "skipped"},
        {"nodeid": "tests/test_c.py::test_boom", "outcome": "error",
         "call": {"duration": 0.0}},
    ],
}


def test_parse_report_counts_outcomes(tmp_path: Path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_MINIMAL_REPORT))

    report = parse_report(report_path, commit="abc123")
    assert report.commit == "abc123"
    assert report.total == 4
    assert report.passed == 1
    assert report.failed == 1
    assert report.errored == 1
    assert report.skipped == 1
    assert report.duration_sec == 0.42


def test_parse_report_sorts_by_nodeid(tmp_path: Path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_MINIMAL_REPORT))
    report = parse_report(report_path)
    node_ids = [t["nodeid"] for t in report.tests]
    assert node_ids == sorted(node_ids)


def test_parse_report_handles_empty_tests(tmp_path: Path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"duration": 0.0, "tests": []}))
    report = parse_report(report_path)
    assert report.total == 0
    assert report.tests == []


def test_write_report_serialises_totals_and_tests(tmp_path: Path):
    report = BaselineReport(
        commit="c1",
        tests=[{"nodeid": "a", "outcome": "passed", "duration": 0.1}],
        passed=1,
        failed=0,
        errored=0,
        skipped=0,
        duration_sec=0.5,
    )
    out = tmp_path / "baseline_report.json"
    write_report(report, out)

    data = json.loads(out.read_text())
    assert data["commit"] == "c1"
    assert data["totals"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
    }
    assert data["duration_sec"] == 0.5
    assert data["tests"] == [
        {"nodeid": "a", "outcome": "passed", "duration": 0.1}
    ]


def _fake_report_run_result(dest_dir: Path, report_payload: dict) -> RunResult:
    (dest_dir / "report.json").write_text(json.dumps(report_payload))
    return RunResult(exit_code=0, stdout="", stderr="", duration_sec=0.1)


def test_run_baseline_orchestrates_build_and_run(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM alpine\n")

    builds: list[tuple] = []

    def fake_builder(df: Path, ctx: Path, tag: str) -> str:
        builds.append((df, ctx, tag))
        return "sha256:fake"

    runs: list[dict] = []

    def fake_runner(image: str, cmd, *, mounts=None, working_dir=None, **kwargs):
        runs.append({"image": image, "cmd": cmd, "mounts": mounts, "wd": working_dir})
        host_dir = next(iter(mounts))
        return _fake_report_run_result(host_dir, _MINIMAL_REPORT)

    report = run_baseline(
        repo,
        tmp_path / "ws",
        commit="deadbeef",
        runner=fake_runner,
        builder=fake_builder,
    )

    assert builds and builds[0][0] == repo / "Dockerfile"
    assert runs and runs[0]["wd"] == "/app"
    assert report.commit == "deadbeef"
    assert report.total == 4


def test_run_baseline_requires_dockerfile(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(FileNotFoundError, match="Dockerfile"):
        run_baseline(repo, tmp_path / "ws")


def test_run_baseline_reports_missing_report(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM alpine\n")

    def fake_builder(df, ctx, tag):
        return "sha256:fake"

    def fake_runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(
            exit_code=2,
            stdout="collection error: ImportError('no module x')",
            stderr="",
            duration_sec=0.1,
        )

    with pytest.raises(RuntimeError, match="did not emit"):
        run_baseline(repo, tmp_path / "ws", runner=fake_runner, builder=fake_builder)
