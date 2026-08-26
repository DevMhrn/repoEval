"""Tests for pipeline.hygiene.coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.common.docker_utils import RunResult
from pipeline.hygiene.coverage import (
    CoverageReport,
    parse_coverage,
    run_coverage,
    write_report,
)

_MINIMAL_COVERAGE = {
    "totals": {"percent_covered": 78.5},
    "files": {
        "src/pkg/core.py": {"summary": {"percent_covered": 92.0}},
        "src/pkg/mutation.py": {"summary": {"percent_covered": 45.0}},
        "src/pkg/util.py": {"summary": {"percent_covered": 60.0}},
    },
}


def test_parse_populates_rates(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(_MINIMAL_COVERAGE))
    report = parse_coverage(p, threshold=0.6, commit="c1")
    assert report.commit == "c1"
    assert report.overall == 0.785
    assert report.line_rate_by_file == {
        "src/pkg/core.py": 0.92,
        "src/pkg/mutation.py": 0.45,
        "src/pkg/util.py": 0.6,
    }
    assert report.module_count == 3


def test_parse_identifies_gaps_below_threshold(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(_MINIMAL_COVERAGE))
    report = parse_coverage(p, threshold=0.7)
    assert report.gaps == ["src/pkg/mutation.py", "src/pkg/util.py"]


def test_parse_gaps_sorted(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(_MINIMAL_COVERAGE))
    report = parse_coverage(p, threshold=0.99)
    assert report.gaps == sorted(report.gaps)


def test_parse_no_files(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps({"totals": {"percent_covered": 0.0}, "files": {}}))
    report = parse_coverage(p)
    assert report.module_count == 0
    assert report.gaps == []
    assert report.overall == 0.0


def test_write_report_serialises(tmp_path: Path):
    report = CoverageReport(
        commit="c",
        line_rate_by_file={"a.py": 0.5, "b.py": 0.9},
        gaps=["a.py"],
        threshold=0.6,
        overall=0.7,
    )
    out = tmp_path / "coverage_report.json"
    write_report(report, out)
    data = json.loads(out.read_text())
    assert data["overall"] == 0.7
    assert data["gaps"] == ["a.py"]
    assert data["line_rate_by_file"] == {"a.py": 0.5, "b.py": 0.9}


def test_run_coverage_orchestrates(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM alpine\n")

    def fake_builder(df, ctx, tag):
        return "sha256:fake"

    def fake_runner(image, cmd, *, mounts=None, **kwargs):
        host_out = next(iter(mounts))
        (host_out / "coverage.json").write_text(json.dumps(_MINIMAL_COVERAGE))
        return RunResult(exit_code=0, stdout="", stderr="", duration_sec=0.2)

    report = run_coverage(
        repo,
        tmp_path / "ws",
        threshold=0.7,
        commit="deadbeef",
        runner=fake_runner,
        builder=fake_builder,
    )
    assert report.commit == "deadbeef"
    assert report.overall == 0.785
    assert "src/pkg/mutation.py" in report.gaps


def test_run_coverage_requires_dockerfile(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Dockerfile"):
        run_coverage(tmp_path, tmp_path / "ws")


def test_run_coverage_missing_report_raises(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM alpine\n")

    def fake_builder(df, ctx, tag):
        return "sha256:fake"

    def fake_runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(exit_code=2, stdout="pytest died", stderr="", duration_sec=0.1)

    with pytest.raises(RuntimeError, match="missing"):
        run_coverage(repo, tmp_path / "ws", runner=fake_runner, builder=fake_builder)
