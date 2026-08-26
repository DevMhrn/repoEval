"""Tests for pipeline.hygiene.stage and reproducibility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.stage import StageContext
from pipeline.hygiene.reproducibility import check as reproducibility_check
from pipeline.hygiene.stage import HygieneStage


def test_reproducibility_pass_on_identical_runs():
    def runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(
            exit_code=0, stdout="hello world\n", stderr="", duration_sec=0.1
        )
    report = reproducibility_check("img", ["echo", "hi"], runner=runner)
    assert report.passed is True
    assert report.first_hash == report.second_hash


def test_reproducibility_pass_after_normalisation_of_volatile_output():
    outputs = iter(
        [
            "collected 5 items in 0.42s\nsession-123 done at 2026-01-01T00:00:00\n",
            "collected 5 items in 3.14s\nsession-999 done at 2026-01-01T12:00:00\n",
        ]
    )

    def runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(
            exit_code=0,
            stdout=next(outputs),
            stderr="",
            duration_sec=0.1,
        )
    report = reproducibility_check("img", ["pytest"], runner=runner)
    assert report.passed is True


def test_reproducibility_fail_on_real_diff():
    outputs = iter(["A: five items\n", "A: six items\n"])

    def runner(image, cmd, *, mounts=None, **kwargs):
        return RunResult(exit_code=0, stdout=next(outputs), stderr="", duration_sec=0.1)

    report = reproducibility_check("img", ["true"], runner=runner)
    assert report.passed is False
    assert "five" in report.diff or "six" in report.diff


def test_hygiene_stage_plan_lists_steps(tmp_path: Path):
    stage = HygieneStage()
    ctx = StageContext(
        repo_path=tmp_path / "repo",
        workspace=tmp_path / "ws",
        config={"hygiene": {}, "docker": {}},
        run_id="hygiene-x",
        extra={"source": "/tmp/whatever"},
    )
    plan = stage.plan(ctx)
    assert plan["stage"] == "hygiene"
    assert "pin_deps" in plan["steps"]
    assert "reproducibility" in plan["steps"]


def test_verify_false_when_report_missing(tmp_path: Path):
    stage = HygieneStage()
    ctx = StageContext(
        repo_path=tmp_path / "repo",
        workspace=tmp_path / "ws",
        config={},
        run_id="r",
    )
    assert stage.verify(ctx) is False


def test_verify_false_when_report_status_not_ok(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hygiene_report.json").write_text(json.dumps({"status": "fail"}))
    stage = HygieneStage()
    ctx = StageContext(
        repo_path=tmp_path / "repo", workspace=ws, config={}, run_id="r"
    )
    assert stage.verify(ctx) is False


def test_verify_true_when_report_status_ok(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hygiene_report.json").write_text(json.dumps({"status": "ok"}))
    stage = HygieneStage()
    ctx = StageContext(
        repo_path=tmp_path / "repo", workspace=ws, config={}, run_id="r"
    )
    assert stage.verify(ctx) is True


def _seed_source_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        "[project]\nname='hygtest'\nversion='0.0.0'\n"
    )
    (path / "hygtest.py").write_text("def add(a, b):\n    return a + b\n")
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
        env={**__import__("os").environ, **env},
    )


def test_hygiene_stage_end_to_end_writes_report_and_pins(tmp_path: Path):
    """End-to-end where every step that needs the network/docker either
    runs (uv) or skips gracefully (docker). This verifies the orchestrator
    still emits a status='ok' report when container steps skip."""
    src = tmp_path / "src"
    _seed_source_repo(src)

    workspace = tmp_path / "ws"
    ctx = StageContext(
        repo_path=workspace / "repo",
        workspace=workspace,
        config={"hygiene": {}, "docker": {}},
        run_id="hygiene-x",
        extra={"source": str(src)},
    )
    stage = HygieneStage()
    result = stage.execute(ctx)

    report_path = workspace / "hygiene_report.json"
    assert report_path.exists(), "expected hygiene_report.json to be written"
    report = json.loads(report_path.read_text())

    # Steps that don't depend on docker must have run.
    assert report["steps"]["ecosystem"] == "python"
    assert "pin_deps" in report["steps"]
    assert "dockerfile" in report["steps"]
    assert "lint" in report["steps"]

    # Overall status must be ok even if docker steps skipped.
    assert report["status"] == "ok"
    assert result.success is True

    # Second call must be a cache hit thanks to the manifest.
    result2 = stage.execute(ctx)
    assert result2.cache_hit is True


def test_verify_reads_malformed_report_as_false(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hygiene_report.json").write_text("not json{")
    stage = HygieneStage()
    ctx = StageContext(
        repo_path=tmp_path / "repo", workspace=ws, config={}, run_id="r"
    )
    assert stage.verify(ctx) is False
