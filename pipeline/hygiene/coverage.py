"""
Per-module coverage analysis.

Re-runs pytest inside the built container with the coverage plugin,
extracts ``coverage.json``, and produces ``coverage_report.json`` with
per-file line rates plus a list of "gap" files below the configured
threshold.

Downstream, Phase 1.12 targets those gap files for LLM-authored test
generation, and Phase 2.9 joins the per-file rate onto the knowledge
graph.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..common.docker_utils import (
    RunResult,
    build_image,
    image_tag,
    run_container,
)

COVERAGE_PATH_IN_CONTAINER = "/tmp/coverage.json"


@dataclass
class CoverageReport:
    commit: str
    line_rate_by_file: dict[str, float] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    threshold: float = 0.6
    overall: float = 0.0

    @property
    def module_count(self) -> int:
        return len(self.line_rate_by_file)


ContainerRunner = Callable[..., RunResult]
ImageBuilder = Callable[..., str]


def run_coverage(
    repo_path: Path,
    workspace: Path,
    *,
    source_root: str = ".",
    threshold: float = 0.6,
    commit: str = "",
    image_hint: str = "coverage",
    runner: ContainerRunner | None = None,
    builder: ImageBuilder | None = None,
) -> CoverageReport:
    dockerfile = repo_path / "Dockerfile"
    if not dockerfile.exists():
        raise FileNotFoundError(f"no Dockerfile at {dockerfile}")

    _build = builder or build_image
    _run = runner or run_container

    tag = image_tag(dockerfile, image_hint)
    _build(dockerfile, repo_path, tag)

    host_out = workspace / "coverage"
    host_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "sh",
        "-c",
        (
            f"pytest --cov={source_root} "
            f"--cov-report=json:{COVERAGE_PATH_IN_CONTAINER} "
            f"|| true; cp {COVERAGE_PATH_IN_CONTAINER} /out/coverage.json 2>/dev/null || true"
        ),
    ]
    result = _run(tag, cmd, mounts={host_out: "/out"}, working_dir="/app")

    raw = host_out / "coverage.json"
    if not raw.exists():
        stdout_head = result.stdout[:1000] if result else ""
        raise RuntimeError(
            f"coverage report missing; container stdout head: {stdout_head}"
        )
    return parse_coverage(raw, threshold=threshold, commit=commit)


def parse_coverage(
    coverage_path: Path,
    *,
    threshold: float = 0.6,
    commit: str = "",
) -> CoverageReport:
    data = json.loads(coverage_path.read_text())
    files = data.get("files", {})

    line_rate_by_file: dict[str, float] = {}
    for path, entry in files.items():
        rate = entry.get("summary", {}).get("percent_covered", 0.0) / 100.0
        line_rate_by_file[path] = round(rate, 4)

    overall = data.get("totals", {}).get("percent_covered", 0.0) / 100.0
    gaps = sorted(p for p, r in line_rate_by_file.items() if r < threshold)

    return CoverageReport(
        commit=commit,
        line_rate_by_file=dict(sorted(line_rate_by_file.items())),
        gaps=gaps,
        threshold=threshold,
        overall=round(overall, 4),
    )


def write_report(report: CoverageReport, out_path: Path) -> Path:
    payload = {
        "commit": report.commit,
        "threshold": report.threshold,
        "overall": report.overall,
        "line_rate_by_file": report.line_rate_by_file,
        "gaps": report.gaps,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return out_path
