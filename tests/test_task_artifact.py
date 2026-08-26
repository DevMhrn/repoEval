"""Tests for pipeline.common.validator.artifact and pipeline.tasks.schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.common.validator.artifact import (
    EVIDENCE_FILE,
    REWARD_PATH_IN_CONTAINER,
    TaskArtifact,
)
from pipeline.tasks.schema import (
    TaskManifest,
    TaskProvenance,
)


def test_constants():
    assert EVIDENCE_FILE == "report.json"
    assert REWARD_PATH_IN_CONTAINER == "/logs/verifier/reward.txt"


def test_artifact_paths_relative_to_folder(tmp_path: Path):
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    assert art.input_dir == tmp_path / "task_001" / "input"
    assert art.solution_dir == tmp_path / "task_001" / "solution"
    assert art.verifier_dir == tmp_path / "task_001" / "verifier"
    assert art.evidence_dir == tmp_path / "task_001" / "evidence"
    assert art.task_json_path == tmp_path / "task_001" / "task.json"
    assert art.instruction_path == tmp_path / "task_001" / "instruction.md"
    assert art.golden_solution_path == tmp_path / "task_001" / "goldenSolution.md"
    assert art.evidence_report_path == tmp_path / "task_001" / "evidence" / "report.json"


def test_ensure_dirs_creates_all(tmp_path: Path):
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    assert art.input_dir.exists()
    assert art.solution_dir.exists()
    assert art.verifier_dir.exists()
    assert art.evidence_dir.exists()


def test_is_shaped_false_when_incomplete(tmp_path: Path):
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    assert art.is_shaped() is False  # task.json missing


def test_is_shaped_true_when_task_json_present(tmp_path: Path):
    art = TaskArtifact(task_folder=tmp_path / "task_001")
    art.ensure_dirs()
    art.task_json_path.write_text("{}")
    assert art.is_shaped() is True


def test_manifest_roundtrip():
    m = TaskManifest(
        id="task_001",
        title="Restore round-trip",
        instruction="Fix serialization to round-trip cleanly.",
        provenance=TaskProvenance(source="history", commit_sha="deadbeef"),
        difficulty="medium",
        difficulty_reason="Requires cross-module reasoning.",
        files_in_scope=["pkg/core.py", "pkg/util.py"],
        module="pkg.core",
        tags=["real-bug", "serialization"],
    )
    reloaded = TaskManifest.model_validate_json(m.model_dump_json())
    assert reloaded == m


def test_manifest_defaults():
    m = TaskManifest(
        id="t",
        title="t",
        instruction="i",
        provenance=TaskProvenance(source="excision"),
        difficulty="easy",
    )
    assert m.validation_status == "pending"
    assert m.verifier_cmd == "bash /verifier/run.sh"
    assert m.files_in_scope == []
    assert m.module == ""


def test_manifest_rejects_unknown_source():
    with pytest.raises(ValidationError):
        TaskManifest(
            id="t",
            title="t",
            instruction="i",
            provenance=TaskProvenance(source="mystery"),  # type: ignore[arg-type]
            difficulty="easy",
        )


def test_manifest_rejects_unknown_difficulty():
    with pytest.raises(ValidationError):
        TaskManifest(
            id="t",
            title="t",
            instruction="i",
            provenance=TaskProvenance(source="history"),
            difficulty="brutal",  # type: ignore[arg-type]
        )


def test_manifest_forbids_extra_fields():
    with pytest.raises(ValidationError):
        TaskManifest(
            id="t",
            title="t",
            instruction="i",
            provenance=TaskProvenance(source="history"),
            difficulty="easy",
            surprise=1,  # type: ignore[call-arg]
        )


def test_provenance_forbids_extra_fields():
    with pytest.raises(ValidationError):
        TaskProvenance(source="history", surprise=1)  # type: ignore[call-arg]
