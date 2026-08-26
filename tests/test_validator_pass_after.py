"""Tests for pipeline.common.validator.checks.pass_after."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.docker_utils import RunResult
from pipeline.common.validator.artifact import TaskArtifact
from pipeline.common.validator.checks import Verdict, pass_after


def _shape(tmp_path: Path, *, with_dockerfile: bool = True) -> TaskArtifact:
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    if with_dockerfile:
        (art.verifier_dir / "Dockerfile").write_text("FROM alpine\n")
    (art.verifier_dir / "run.sh").write_text(
        "#!/bin/sh\nmkdir -p /logs/verifier\necho 1 > /logs/verifier/reward.txt\n"
    )
    (art.solution_dir / "src.py").write_text("def x(): return 1\n")
    return art


def _reward_writer(reward: str):
    def runner(image, cmd, *, mounts=None, working_dir=None, **kwargs):
        assert mounts is not None
        logs_dir = None
        for host, target in mounts.items():
            if target == "/logs":
                logs_dir = host
                break
        assert logs_dir is not None, "test runner needs /logs mount"
        (logs_dir / "verifier").mkdir(parents=True, exist_ok=True)
        (logs_dir / "verifier" / "reward.txt").write_text(reward)
        return RunResult(exit_code=0, stdout="", stderr="", duration_sec=0.1)
    return runner


def _fake_builder(df: Path, ctx: Path, tag: str) -> str:
    return f"sha256:fake:{tag}"


def test_pass_after_passes_on_reward_one(tmp_path: Path):
    art = _shape(tmp_path)
    result = pass_after(art, runner=_reward_writer("1.0"), builder=_fake_builder)
    assert result.verdict == Verdict.PASS
    assert result.reason.startswith("reward=1.0")


def test_pass_after_fails_on_reward_zero(tmp_path: Path):
    art = _shape(tmp_path)
    result = pass_after(art, runner=_reward_writer("0"), builder=_fake_builder)
    assert result.verdict == Verdict.FAIL
    assert result.reason.startswith("reward=0")


def test_pass_after_fails_on_missing_reward_file(tmp_path: Path):
    art = _shape(tmp_path)

    def runner_no_write(image, cmd, *, mounts=None, **kwargs):
        return RunResult(exit_code=2, stdout="crash", stderr="", duration_sec=0.1)

    result = pass_after(art, runner=runner_no_write, builder=_fake_builder)
    assert result.verdict == Verdict.FAIL
    assert "no reward" in result.reason.lower()


def test_pass_after_errors_when_no_verifier_image_and_no_dockerfile(tmp_path: Path):
    art = _shape(tmp_path, with_dockerfile=False)
    result = pass_after(
        art,
        runner=_reward_writer("1.0"),
        builder=_fake_builder,
    )
    assert result.verdict == Verdict.ERROR
    assert "no verifier_image" in result.reason


def test_pass_after_reuses_provided_image_tag(tmp_path: Path):
    art = _shape(tmp_path)
    art.verifier_image = "prebuilt:tag"
    builds: list = []

    def spy_builder(df, ctx, tag):
        builds.append(tag)
        return "sha:x"

    pass_after(art, runner=_reward_writer("1.0"), builder=spy_builder)
    assert builds == []  # no rebuild


def test_pass_after_evidence_written(tmp_path: Path):
    art = _shape(tmp_path)
    result = pass_after(
        art, runner=_reward_writer("1.0"), builder=_fake_builder
    )
    assert result.evidence_path.exists()
    data = json.loads(result.evidence_path.read_text())
    assert data["verdict"] == "pass"
    assert data["reward"] == 1.0


def test_pass_after_reward_non_numeric_is_fail(tmp_path: Path):
    art = _shape(tmp_path)
    result = pass_after(
        art, runner=_reward_writer("hello"), builder=_fake_builder
    )
    assert result.verdict == Verdict.FAIL
