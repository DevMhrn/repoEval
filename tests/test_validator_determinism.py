"""Tests for pipeline.common.validator.checks.determinism."""

from __future__ import annotations

from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.validator.artifact import TaskArtifact
from pipeline.common.validator.checks import Verdict, determinism


def _shape(tmp_path: Path) -> TaskArtifact:
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    (art.verifier_dir / "Dockerfile").write_text("FROM alpine\n")
    (art.verifier_dir / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (art.solution_dir / "src.py").write_text("def x(): return 1\n")
    return art


def _fake_builder(df, ctx, tag):
    return f"sha:{tag}"


def _stable_runner(reward: str = "1.0", stdout: str = "pytest passed\n"):
    def run(image, cmd, *, mounts=None, **kwargs):
        for host, target in mounts.items():
            if target == "/logs":
                (host / "verifier").mkdir(parents=True, exist_ok=True)
                (host / "verifier" / "reward.txt").write_text(reward)
        return RunResult(exit_code=0, stdout=stdout, stderr="", duration_sec=0.1)
    return run


def _flaky_reward_runner(rewards: list[str]):
    it = iter(rewards)

    def run(image, cmd, *, mounts=None, **kwargs):
        r = next(it)
        for host, target in mounts.items():
            if target == "/logs":
                (host / "verifier").mkdir(parents=True, exist_ok=True)
                (host / "verifier" / "reward.txt").write_text(r)
        return RunResult(exit_code=0, stdout="", stderr="", duration_sec=0.1)
    return run


def _flaky_stdout_runner(stdouts: list[str], reward: str = "1"):
    it = iter(stdouts)

    def run(image, cmd, *, mounts=None, **kwargs):
        s = next(it)
        for host, target in mounts.items():
            if target == "/logs":
                (host / "verifier").mkdir(parents=True, exist_ok=True)
                (host / "verifier" / "reward.txt").write_text(reward)
        return RunResult(exit_code=0, stdout=s, stderr="", duration_sec=0.1)
    return run


def test_determinism_pass_when_all_runs_agree(tmp_path: Path):
    result = determinism(
        _shape(tmp_path),
        repeats=3,
        runner=_stable_runner(reward="1.0"),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.PASS
    assert result.metadata["rewards_agree"] is True


def test_determinism_fail_when_reward_flakes(tmp_path: Path):
    result = determinism(
        _shape(tmp_path),
        repeats=3,
        runner=_flaky_reward_runner(["1", "0", "1"]),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.FAIL
    assert result.metadata["rewards_agree"] is False


def test_determinism_pass_ignores_volatile_stdout(tmp_path: Path):
    # Different timing/timestamps but same behavior.
    stdouts = [
        "===== 3 passed in 0.42s =====\nsession abc\n2026-01-01T00:00:00\n",
        "===== 3 passed in 3.14s =====\nsession abc\n2026-01-01T12:00:00\n",
        "===== 3 passed in 0.10s =====\nsession abc\n2026-01-01T18:00:00\n",
    ]
    result = determinism(
        _shape(tmp_path),
        repeats=3,
        runner=_flaky_stdout_runner(stdouts),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.PASS


def test_determinism_fail_when_behaviour_actually_differs(tmp_path: Path):
    stdouts = [
        "===== 3 passed =====\n",
        "===== 2 passed, 1 failed =====\n",
        "===== 3 passed =====\n",
    ]
    result = determinism(
        _shape(tmp_path),
        repeats=3,
        runner=_flaky_stdout_runner(stdouts),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.FAIL
    assert result.metadata["stdouts_agree"] is False


def test_determinism_repeats_less_than_two_errors(tmp_path: Path):
    result = determinism(
        _shape(tmp_path),
        repeats=1,
        runner=_stable_runner(),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.ERROR


def test_determinism_records_repeat_count_in_metadata(tmp_path: Path):
    result = determinism(
        _shape(tmp_path),
        repeats=4,
        runner=_stable_runner(),
        builder=_fake_builder,
    )
    assert result.metadata["repeats"] == 4
    assert len(result.metadata["rewards"]) == 4
