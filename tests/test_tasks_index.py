"""Tests for pipeline.tasks.emit_manifest.emit_tasks_index."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.validator.artifact import TaskArtifact
from pipeline.tasks.emit_manifest import emit_manifest, emit_tasks_index
from pipeline.tasks.schema import TaskManifest, TaskProvenance


def _mk_task(tasks_dir: Path, task_id: str, source: str, module: str = "") -> None:
    art = TaskArtifact(task_folder=tasks_dir / task_id)
    art.ensure_dirs()
    manifest = TaskManifest(
        id=task_id,
        title=f"Task {task_id}",
        instruction="i",
        provenance=TaskProvenance(source=source),
        difficulty="medium",
        module=module,
        tags=[source],
    )
    emit_manifest(art, manifest)


def test_index_contains_one_entry_per_task(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    _mk_task(tasks_dir, "task_002", "history", module="pkg.a")
    _mk_task(tasks_dir, "task_001", "excision", module="pkg.b")
    _mk_task(tasks_dir, "task_003", "net_new", module="pkg.c")

    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    entries = json.loads(out.read_text())
    assert len(entries) == 3
    ids = [e["id"] for e in entries]
    assert ids == ["task_001", "task_002", "task_003"]


def test_index_records_expected_fields(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    _mk_task(tasks_dir, "task_001", "history", module="pkg.core")

    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    entry = json.loads(out.read_text())[0]
    assert entry["source"] == "history"
    assert entry["module"] == "pkg.core"
    assert entry["difficulty"] == "medium"
    assert entry["validation_status"] == "pending"
    assert entry["verifier_cmd"] == "bash /verifier/run.sh"
    assert "history" in entry["tags"]


def test_index_skips_folders_without_task_json(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task_no_manifest").mkdir()
    _mk_task(tasks_dir, "task_002", "excision")

    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    entries = json.loads(out.read_text())
    assert [e["id"] for e in entries] == ["task_002"]


def test_index_skips_malformed_task_json(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task_bad").mkdir()
    (tasks_dir / "task_bad" / "task.json").write_text("not json{")
    _mk_task(tasks_dir, "task_good", "history")

    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    entries = json.loads(out.read_text())
    assert [e["id"] for e in entries] == ["task_good"]


def test_index_empty_when_no_tasks(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    assert json.loads(out.read_text()) == []


def test_index_is_deterministic(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    _mk_task(tasks_dir, "task_a", "history")
    _mk_task(tasks_dir, "task_b", "excision")

    out = tmp_path / "tasks.json"
    emit_tasks_index(tasks_dir, out)
    first = out.read_text()
    emit_tasks_index(tasks_dir, out)
    assert out.read_text() == first
