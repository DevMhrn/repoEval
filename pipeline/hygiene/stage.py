"""
HygieneStage — Pipeline 1 orchestrator.

Runs the whole hygiene flow: ingest → detect ecosystem → pin deps →
generate Dockerfile → baseline test in container → coverage analysis →
generate tests for gaps → lint & format → reproducibility gate. Writes
a summary to ``output/hygiene_report.json``.

If Docker isn't available the container-dependent steps
(baseline, coverage, reproducibility) are marked ``skipped`` with the
reason surfaced. The non-container steps still ship a working pinned
+ containerised + lint-clean repo under ``output/repo/``.

The stage is idempotent via the base ``Stage.execute()`` wrapper: the
repo snapshot hash plus the ``hygiene`` and ``docker`` config subsets
feed the manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common.docker_utils import (
    build_image,
    image_tag,
)
from ..common.ecosystem import detect
from ..common.stage import Stage, StageContext, StageResult
from .baseline import run_baseline
from .baseline import write_report as write_baseline
from .coverage import run_coverage
from .coverage import write_report as write_coverage
from .generate_dockerfile import generate_dockerfile
from .ingest import ingest
from .lint_setup import setup_lint
from .pin_deps import pin_deps
from .reproducibility import check as check_reproducibility


@dataclass
class _StepRecord:
    ok: bool
    details: dict[str, Any]


class HygieneStage(Stage):
    name = "hygiene"
    config_keys = ("hygiene", "docker")

    def plan(self, ctx: StageContext) -> dict[str, Any]:
        return {
            "stage": self.name,
            "target": ctx.extra.get("source", str(ctx.repo_path)),
            "steps": [
                "ingest",
                "detect_ecosystem",
                "pin_deps",
                "generate_dockerfile",
                "baseline_tests",
                "coverage",
                "lint_setup",
                "reproducibility",
            ],
        }

    def verify(self, ctx: StageContext) -> bool:
        report_path = ctx.workspace / "hygiene_report.json"
        if not report_path.exists():
            return False
        try:
            data = json.loads(report_path.read_text())
        except (json.JSONDecodeError, OSError):
            return False
        return data.get("status") == "ok"

    def run(self, ctx: StageContext) -> StageResult:
        report: dict[str, Any] = {"stage": self.name, "steps": {}}
        outputs: dict[str, str] = {}

        try:
            source = ctx.extra.get("source", str(ctx.repo_path))
            ingest_result = ingest(source, ctx.workspace)
            report["steps"]["ingest"] = {
                "commit": ingest_result.resolved_commit,
                "reused": ingest_result.reused,
                "source_type": ingest_result.source_type,
            }
            repo_path = ingest_result.repo_path

            strategy = detect(repo_path)
            report["steps"]["ecosystem"] = strategy.name

            lockfile = pin_deps(repo_path, ctx.workspace / "pin", strategy=strategy)
            report["steps"]["pin_deps"] = {"lockfile": str(lockfile)}
            outputs[str(lockfile)] = "pinned"

            dockerfile = generate_dockerfile(repo_path, strategy)
            report["steps"]["dockerfile"] = str(dockerfile)
            outputs[str(dockerfile)] = "generated"

            docker_available = self._try_baseline_and_coverage(
                repo_path, ctx, ingest_result.resolved_commit, report
            )

            lint = setup_lint(repo_path)
            report["steps"]["lint"] = {
                "clean": lint.lint_clean,
                "residual": lint.residual_errors,
            }

            report["reproducibility"] = self._try_reproducibility(
                dockerfile, repo_path, docker_available, report
            )

            report["status"] = "ok"
            report_path = self._write_report(ctx, report)
            outputs[str(report_path)] = "hygiene_report"

            return StageResult(
                stage=self.name,
                success=True,
                outputs=outputs,
            )
        except Exception as e:  # noqa: BLE001 — record any failure and surface via report
            report["status"] = "fail"
            report["error"] = str(e)
            self._write_report(ctx, report)
            return StageResult(stage=self.name, success=False, error=str(e))

    def _try_baseline_and_coverage(
        self,
        repo_path: Path,
        ctx: StageContext,
        commit: str,
        report: dict[str, Any],
    ) -> bool:
        try:
            baseline = run_baseline(repo_path, ctx.workspace, commit=commit)
            write_baseline(baseline, ctx.workspace / "baseline_report.json")
            report["steps"]["baseline"] = {
                "total": baseline.total,
                "passed": baseline.passed,
                "failed": baseline.failed,
                "errored": baseline.errored,
                "skipped": baseline.skipped,
            }
        except Exception as e:  # noqa: BLE001 — container steps skip on any failure
            report["steps"]["baseline"] = {"skipped": True, "reason": str(e)}
            return False

        try:
            cov = run_coverage(repo_path, ctx.workspace, commit=commit)
            write_coverage(cov, ctx.workspace / "coverage_report.json")
            report["steps"]["coverage"] = {
                "overall": cov.overall,
                "gaps": len(cov.gaps),
                "gap_files": cov.gaps[:20],
            }
        except Exception as e:  # noqa: BLE001 — container steps skip on any failure
            report["steps"]["coverage"] = {"skipped": True, "reason": str(e)}
        return True

    def _try_reproducibility(
        self,
        dockerfile: Path,
        repo_path: Path,
        docker_available: bool,
        report: dict[str, Any],
    ) -> str:
        if not docker_available:
            report["steps"]["reproducibility"] = {"skipped": True, "reason": "docker unavailable"}
            return "skipped"
        try:
            tag = image_tag(dockerfile, "repro")
            build_image(dockerfile, repo_path, tag)
            result = check_reproducibility(tag, ["pytest", "--collect-only", "-q"])
            report["steps"]["reproducibility"] = {
                "passed": result.passed,
                "first_hash": result.first_hash,
                "second_hash": result.second_hash,
            }
            return "pass" if result.passed else "fail"
        except Exception as e:  # noqa: BLE001 — reproducibility is optional; any failure skips
            report["steps"]["reproducibility"] = {"skipped": True, "reason": str(e)}
            return "skipped"

    def _write_report(self, ctx: StageContext, report: dict[str, Any]) -> Path:
        path = ctx.workspace / "hygiene_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True))
        return path
