"""Tests for pipeline.tasks.golden."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.llm_client import LLMClient, fixture_key
from pipeline.common.prompts.loader import load_prompt
from pipeline.tasks.golden import compute_diff, emit_golden_solution
from pipeline.tasks.schema import TaskManifest, TaskProvenance


def _prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "golden_rationale.md").write_text(
        "title={title}\nsrc={source}\nins={instruction}\ndiff={diff}\n"
    )
    return d


def _seed_fixture(fixtures: Path, model: str, prompt: str, response_text: str):
    key = fixture_key(model, 0.0, None, prompt)
    fixtures.mkdir(exist_ok=True)
    (fixtures / f"{key}.json").write_text(
        json.dumps(
            {
                "key": key,
                "model": model,
                "temperature": 0.0,
                "system": None,
                "prompt": prompt,
                "response_text": response_text,
                "input_tokens": 1,
                "output_tokens": 1,
                "saved_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )


def _manifest() -> TaskManifest:
    return TaskManifest(
        id="task_001",
        title="Fix parse whitespace",
        instruction="Handle leading whitespace in input.",
        provenance=TaskProvenance(source="history"),
        difficulty="medium",
        files_in_scope=["pkg/core.py"],
    )


def test_compute_diff_scoped_to_files_in_scope(tmp_path: Path):
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solution"
    (input_dir / "pkg").mkdir(parents=True)
    (solution_dir / "pkg").mkdir(parents=True)
    (input_dir / "pkg" / "core.py").write_text("def parse(s):\n    return s\n")
    (solution_dir / "pkg" / "core.py").write_text(
        "def parse(s):\n    return s.strip()\n"
    )
    (input_dir / "pkg" / "other.py").write_text("x = 1\n")
    (solution_dir / "pkg" / "other.py").write_text("x = 2\n")

    diff = compute_diff(input_dir, solution_dir, ["pkg/core.py"])
    assert "pkg/core.py" in diff
    assert "pkg/other.py" not in diff
    assert "strip()" in diff


def test_compute_diff_falls_back_to_all_differing_files(tmp_path: Path):
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solution"
    (input_dir / "a.py").parent.mkdir(parents=True, exist_ok=True)
    (input_dir / "a.py").write_text("old\n")
    (solution_dir / "a.py").parent.mkdir(parents=True, exist_ok=True)
    (solution_dir / "a.py").write_text("new\n")

    diff = compute_diff(input_dir, solution_dir, [])
    assert "a.py" in diff


def test_emit_writes_markdown_with_prose_and_diff(tmp_path: Path):
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solution"
    (input_dir / "pkg").mkdir(parents=True)
    (solution_dir / "pkg").mkdir(parents=True)
    (input_dir / "pkg" / "core.py").write_text("def parse(s):\n    return s\n")
    (solution_dir / "pkg" / "core.py").write_text(
        "def parse(s):\n    return s.strip()\n"
    )

    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    manifest = _manifest()
    diff = compute_diff(input_dir, solution_dir, manifest.files_in_scope)

    tpl = load_prompt("golden_rationale", prompts_dir=prompts_dir)
    prompt = tpl.render(
        title=manifest.title,
        source=manifest.provenance.source,
        instruction=manifest.instruction,
        diff=diff,
    )
    _seed_fixture(
        fixtures, "m", prompt,
        "The fix strips leading whitespace so downstream lookups behave correctly.",
    )

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    out_path = tmp_path / "task_001" / "goldenSolution.md"
    emit_golden_solution(
        input_dir, solution_dir, manifest, llm, out_path,
        prompts_dir=prompts_dir,
    )

    content = out_path.read_text()
    assert "# Golden Solution" in content
    assert "task_001" in content
    assert "```diff" in content
    assert "strip()" in content
    assert "leading whitespace" in content


def test_emit_handles_empty_diff(tmp_path: Path):
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solution"
    (input_dir / "a.py").parent.mkdir(parents=True)
    (solution_dir / "a.py").parent.mkdir(parents=True, exist_ok=True)
    (input_dir / "a.py").write_text("same\n")
    (solution_dir / "a.py").write_text("same\n")

    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    manifest = TaskManifest(
        id="t",
        title="T",
        instruction="i",
        provenance=TaskProvenance(source="history"),
        difficulty="easy",
        files_in_scope=["a.py"],
    )
    tpl = load_prompt("golden_rationale", prompts_dir=prompts_dir)
    prompt = tpl.render(
        title=manifest.title,
        source=manifest.provenance.source,
        instruction=manifest.instruction,
        diff="",
    )
    _seed_fixture(fixtures, "m", prompt, "No diff — trivial task.")

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    out_path = tmp_path / "goldenSolution.md"
    emit_golden_solution(
        input_dir, solution_dir, manifest, llm, out_path,
        prompts_dir=prompts_dir,
    )
    assert "(no changes detected)" in out_path.read_text()


def test_diff_shows_added_file_when_input_missing(tmp_path: Path):
    input_dir = tmp_path / "input"
    solution_dir = tmp_path / "solution"
    input_dir.mkdir()
    solution_dir.mkdir()
    (solution_dir / "new.py").write_text("hello\n")

    diff = compute_diff(input_dir, solution_dir, [])
    assert "new.py" in diff
