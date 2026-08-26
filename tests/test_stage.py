"""Tests for pipeline.common.stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.common.stage import Stage, StageContext, StageResult


class _CountingStage(Stage):
    name = "dummy"
    config_keys = ("dummy",)

    def __init__(self) -> None:
        self.run_count = 0
        self.verify_after_run: bool = True

    def plan(self, ctx: StageContext) -> dict[str, Any]:
        return {"planned": True}

    def run(self, ctx: StageContext) -> StageResult:
        self.run_count += 1
        out = ctx.workspace / "dummy_out.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"hello {self.run_count}")
        return StageResult(stage=self.name, success=True, outputs={out.as_posix(): "x"})

    def verify(self, ctx: StageContext) -> bool:
        if not self.verify_after_run:
            return False
        return (ctx.workspace / "dummy_out.txt").exists()


def _mk_ctx(tmp_path: Path, config: dict[str, Any] | None = None) -> StageContext:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir(exist_ok=True)
    workspace.mkdir(exist_ok=True)
    (repo / "a.py").write_text("print('a')\n")
    (repo / "b.py").write_text("print('b')\n")
    return StageContext(
        repo_path=repo,
        workspace=workspace,
        config=config or {"dummy": {"opt": 1}},
        run_id="dummy-run-1",
    )


def test_snapshot_hash_is_stable(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    h1 = ctx.snapshot_hash(("dummy",))
    h2 = ctx.snapshot_hash(("dummy",))
    assert h1 == h2


def test_snapshot_hash_changes_with_repo_content(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    h1 = ctx.snapshot_hash(("dummy",))
    (ctx.repo_path / "a.py").write_text("print('changed')\n")
    h2 = ctx.snapshot_hash(("dummy",))
    assert h1 != h2


def test_snapshot_hash_changes_with_relevant_config(tmp_path: Path):
    ctx1 = _mk_ctx(tmp_path, config={"dummy": {"opt": 1}})
    ctx2 = _mk_ctx(tmp_path, config={"dummy": {"opt": 2}})
    assert ctx1.snapshot_hash(("dummy",)) != ctx2.snapshot_hash(("dummy",))


def test_snapshot_hash_stable_across_irrelevant_config(tmp_path: Path):
    ctx1 = _mk_ctx(tmp_path, config={"dummy": {"opt": 1}, "unrelated": {"x": 1}})
    ctx2 = _mk_ctx(tmp_path, config={"dummy": {"opt": 1}, "unrelated": {"x": 999}})
    assert ctx1.snapshot_hash(("dummy",)) == ctx2.snapshot_hash(("dummy",))


def test_snapshot_hash_ignores_common_cache_dirs(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    h1 = ctx.snapshot_hash(("dummy",))
    for name in (".git", ".venv", "__pycache__", ".ruff_cache"):
        d = ctx.repo_path / name
        d.mkdir()
        (d / "stuff").write_text("noise")
    h2 = ctx.snapshot_hash(("dummy",))
    assert h1 == h2


def test_first_execute_writes_manifest(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    result = stage.execute(ctx)
    assert result.success
    assert not result.cache_hit
    assert stage.run_count == 1
    manifest_path = ctx.workspace / ".manifests" / "dummy.json"
    assert manifest_path.exists()
    assert result.manifest_path == manifest_path


def test_second_execute_is_cache_hit(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    stage.execute(ctx)
    result = stage.execute(ctx)
    assert result.success
    assert result.cache_hit
    assert stage.run_count == 1  # not incremented


def test_editing_repo_forces_rerun(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    stage.execute(ctx)
    (ctx.repo_path / "a.py").write_text("print('changed')\n")
    result = stage.execute(ctx)
    assert not result.cache_hit
    assert stage.run_count == 2


def test_editing_relevant_config_forces_rerun(tmp_path: Path):
    ctx = _mk_ctx(tmp_path, config={"dummy": {"opt": 1}})
    stage = _CountingStage()
    stage.execute(ctx)
    ctx.config["dummy"]["opt"] = 2
    result = stage.execute(ctx)
    assert not result.cache_hit
    assert stage.run_count == 2


def test_missing_verify_output_invalidates_cache(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    stage.execute(ctx)
    (ctx.workspace / "dummy_out.txt").unlink()
    result = stage.execute(ctx)
    assert not result.cache_hit
    assert stage.run_count == 2


def test_verify_false_after_run_marks_failure(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    stage.verify_after_run = False
    result = stage.execute(ctx)
    assert not result.success
    assert result.error == "verify() returned False after run()"
    assert not (ctx.workspace / ".manifests" / "dummy.json").exists()


def test_needs_rerun_true_when_manifest_missing(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    assert stage.needs_rerun(ctx) is True


def test_needs_rerun_true_when_manifest_corrupt(tmp_path: Path):
    ctx = _mk_ctx(tmp_path)
    stage = _CountingStage()
    stage.execute(ctx)
    stage.manifest_path(ctx).write_text("not-json{")
    assert stage.needs_rerun(ctx) is True


def test_stage_result_defaults_are_safe():
    r = StageResult(stage="x", success=True)
    assert r.outputs == {}
    assert r.duration_sec == 0.0
    assert r.log_path is None
    assert r.error is None
    assert r.cache_hit is False
