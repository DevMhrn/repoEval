"""Tests for pipeline.tasks.builders.net_new."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.llm_client import LLMClient, fixture_key
from pipeline.common.prompts.loader import load_prompt
from pipeline.tasks.builders.net_new import build_net_new_task
from pipeline.tasks.miners.net_new import NetNewProposal


def _prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "net_new_tests.md").write_text(
        "TESTS module={module} title={title}\n{description}\n"
    )
    (d / "net_new_solution.md").write_text(
        "IMPL module={module} title={title}\n{description}\n"
        "tests:\n{test_source}\n"
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


def _seed_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("def existing(): return 1\n")


def _proposal() -> NetNewProposal:
    return NetNewProposal(
        title="Add hello function",
        module="pkg.core",
        description="A function `hello(name)` returning 'hi, <name>!'",
        est_loc=10,
    )


def _prepare_fixtures(prompts_dir: Path, fixtures: Path, model: str,
                     tests_source: str, impl_source: str) -> None:
    prop = _proposal()

    tpl_tests = load_prompt("net_new_tests", prompts_dir=prompts_dir)
    tests_prompt = tpl_tests.render(
        module=prop.module, title=prop.title, description=prop.description,
    )
    _seed_fixture(fixtures, model, tests_prompt, tests_source)

    tpl_impl = load_prompt("net_new_solution", prompts_dir=prompts_dir)
    impl_prompt = tpl_impl.render(
        module=prop.module, title=prop.title, description=prop.description,
        test_source=tests_source.strip() + "\n",
    )
    _seed_fixture(fixtures, model, impl_prompt, impl_source)


def test_builds_full_task_folder(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    _prepare_fixtures(
        prompts_dir, fixtures, "m",
        tests_source=(
            "from pkg.core import hello\n"
            "def test_hi(): assert hello('bob') == 'hi, bob!'\n"
        ),
        impl_source="def hello(name):\n    return f'hi, {name}!'\n",
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)

    artifact = build_net_new_task(
        _proposal(),
        repo,
        tmp_path / "tasks" / "task_001",
        llm,
        task_id="task_001",
        dockerfile_contents="FROM python:3.11-slim\n",
        prompts_dir=prompts_dir,
    )

    assert (artifact.input_dir / "pkg" / "core.py").read_text() == "def existing(): return 1\n"
    solution_src = (artifact.solution_dir / "pkg" / "core.py").read_text()
    assert "def existing():" in solution_src
    assert "def hello(name):" in solution_src

    tests_dir = artifact.verifier_dir / "tests"
    test_files = list(tests_dir.glob("*.py"))
    assert len(test_files) == 1
    assert "def test_hi" in test_files[0].read_text()

    assert (artifact.verifier_dir / "Dockerfile").exists()
    assert (artifact.verifier_dir / "run.sh").exists()

    data = json.loads(artifact.task_json_path.read_text())
    assert data["provenance"]["source"] == "net_new"
    assert data["module"] == "pkg.core"
    assert "net-new" in data["tags"]


def test_input_unchanged_solution_extended(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    _prepare_fixtures(
        prompts_dir, fixtures, "m",
        tests_source="assert True\n",
        impl_source="def hello(name):\n    return name\n",
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    artifact = build_net_new_task(
        _proposal(),
        repo,
        tmp_path / "task_001",
        llm,
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
        prompts_dir=prompts_dir,
    )
    input_src = (artifact.input_dir / "pkg" / "core.py").read_text()
    solution_src = (artifact.solution_dir / "pkg" / "core.py").read_text()
    assert "def hello" not in input_src
    assert "def hello" in solution_src


def test_strips_fences_from_impl(tmp_path: Path):
    repo = tmp_path / "repo"
    _seed_repo(repo)
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    _prepare_fixtures(
        prompts_dir, fixtures, "m",
        tests_source="assert True\n",
        impl_source="```python\ndef hello(): pass\n```",
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    artifact = build_net_new_task(
        _proposal(),
        repo,
        tmp_path / "task_001",
        llm,
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
        prompts_dir=prompts_dir,
    )
    solution_src = (artifact.solution_dir / "pkg" / "core.py").read_text()
    assert "```" not in solution_src
    assert "def hello" in solution_src


def test_module_resolution_falls_back_to_package_init(tmp_path: Path):
    """Package with __init__.py — impl should append there."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pkgx").mkdir()
    (repo / "pkgx" / "__init__.py").write_text("")

    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    prop = NetNewProposal(
        title="t", module="pkgx", description="d",
    )
    tpl_tests = load_prompt("net_new_tests", prompts_dir=prompts_dir)
    tpl_impl = load_prompt("net_new_solution", prompts_dir=prompts_dir)
    tests_source = "assert True\n"
    impl_source = "def added(): return 1\n"
    _seed_fixture(
        fixtures, "m",
        tpl_tests.render(module=prop.module, title=prop.title, description=prop.description),
        tests_source,
    )
    _seed_fixture(
        fixtures, "m",
        tpl_impl.render(
            module=prop.module, title=prop.title, description=prop.description,
            test_source=tests_source.strip() + "\n",
        ),
        impl_source,
    )

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    artifact = build_net_new_task(
        prop, repo, tmp_path / "task_001", llm,
        task_id="task_001",
        dockerfile_contents="FROM alpine\n",
        prompts_dir=prompts_dir,
    )
    init_src = (artifact.solution_dir / "pkgx" / "__init__.py").read_text()
    assert "def added" in init_src
