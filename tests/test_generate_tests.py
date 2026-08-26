"""Tests for pipeline.hygiene.bug_injector and generate_tests orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.common.llm_client import LLMClient, fixture_key
from pipeline.hygiene.bug_injector import (
    apply_mutations_to_function,
    run_test_against_source,
)
from pipeline.hygiene.generate_tests import (
    _strip_code_fences,
    _target_function_names,
    generate_tests_for_module,
)


def test_flip_bool_mutation_produces_flipped_source():
    src = "def is_positive(x):\n    return x > 0 and True\n"
    mutants = apply_mutations_to_function(src, "is_positive")
    flip = next((m for m in mutants if m.name == "flip_bool"), None)
    assert flip is not None
    assert "False" in flip.source


def test_swap_addsub_mutation():
    src = "def add(a, b):\n    return a + b\n"
    mutants = apply_mutations_to_function(src, "add")
    swap = next((m for m in mutants if m.name == "swap_addsub"), None)
    assert swap is not None
    assert "a - b" in swap.source


def test_perturb_int_mutation():
    src = "def two():\n    return 2\n"
    mutants = apply_mutations_to_function(src, "two")
    perturb = next((m for m in mutants if m.name == "perturb_int"), None)
    assert perturb is not None
    assert "3" in perturb.source


def test_swap_eq_neq_mutation():
    src = "def is_ok(x):\n    return x == 0\n"
    mutants = apply_mutations_to_function(src, "is_ok")
    swap = next((m for m in mutants if m.name == "swap_eq_neq"), None)
    assert swap is not None
    assert "!=" in swap.source


def test_mutations_only_touch_target_function():
    src = (
        "def keep(x):\n    return x + 1\n\n"
        "def target(y):\n    return y == 5\n"
    )
    mutants = apply_mutations_to_function(src, "target")
    for m in mutants:
        assert "def keep(x):\n    return x + 1" in m.source


def test_no_mutations_if_function_absent():
    src = "def a():\n    return 1\n"
    assert apply_mutations_to_function(src, "not_there") == []


def test_no_mutations_on_syntax_error():
    assert apply_mutations_to_function("def broken(:\n", "broken") == []


def test_run_test_against_source_passes_on_correct_module(tmp_path: Path):
    module_source = "def add(a, b):\n    return a + b\n"
    test_source = (
        "from add_mod import add\n"
        "def test_add():\n    assert add(2, 3) == 5\n"
        "def test_add_negative():\n    assert add(-1, 1) == 0\n"
    )
    passed, _ = run_test_against_source("add_mod", module_source, test_source)
    assert passed is True


def test_run_test_against_source_fails_on_mutant(tmp_path: Path):
    module_source = "def add(a, b):\n    return a + b\n"
    mutants = apply_mutations_to_function(module_source, "add")
    test_source = (
        "from add_mod import add\n"
        "def test_add():\n    assert add(2, 3) == 5\n"
    )
    swap = next(m for m in mutants if m.name == "swap_addsub")
    passed, _ = run_test_against_source("add_mod", swap.source, test_source)
    assert passed is False


def test_target_function_names_intersects_module_and_calls():
    module = (
        "def used():\n    return 1\n\n"
        "def unused():\n    return 2\n"
    )
    tests = (
        "from x import used\n"
        "def test_a():\n    assert used() == 1\n"
    )
    assert _target_function_names(tests, module) == ["used"]


def test_strip_code_fences_removes_python_block():
    fenced = "```python\ndef test_x():\n    assert 1 == 1\n```"
    stripped = _strip_code_fences(fenced)
    assert stripped.startswith("def test_x():")
    assert "```" not in stripped


def test_strip_code_fences_plain_text_unchanged():
    plain = "def test_y(): pass\n"
    assert _strip_code_fences(plain) == plain


def _seed_fixture(fixtures: Path, model: str, prompt: str, response_text: str) -> None:
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


def test_generate_tests_keeps_tests_that_kill_mutants(tmp_path: Path):
    module_path = tmp_path / "adder.py"
    module_path.write_text("def add(a, b):\n    return a + b\n")

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "generate_tests.md").write_text(
        "Module path: {module_path}\nSource:\n{module_source}\n"
    )

    fixtures = tmp_path / "fx"
    from pipeline.common.prompts.loader import load_prompt
    tpl = load_prompt("generate_tests", prompts_dir=prompts_dir)
    prompt_text = tpl.render(
        module_path=module_path.as_posix(),
        module_source=module_path.read_text(),
    )
    good_tests = (
        "from adder import add\n"
        "def test_two_plus_three():\n    assert add(2, 3) == 5\n"
        "def test_neg():\n    assert add(-2, -3) == -5\n"
    )
    _seed_fixture(fixtures, "m", prompt_text, good_tests)

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    report = generate_tests_for_module(
        module_path, llm, prompts_dir=prompts_dir
    )
    assert report.kept is True
    assert report.mutants_killed  # non-empty


def test_generate_tests_rejects_coverage_theater(tmp_path: Path):
    module_path = tmp_path / "adder.py"
    module_path.write_text("def add(a, b):\n    return a + b\n")

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "generate_tests.md").write_text(
        "Module path: {module_path}\nSource:\n{module_source}\n"
    )

    fixtures = tmp_path / "fx"
    from pipeline.common.prompts.loader import load_prompt
    tpl = load_prompt("generate_tests", prompts_dir=prompts_dir)
    prompt_text = tpl.render(
        module_path=module_path.as_posix(),
        module_source=module_path.read_text(),
    )
    # Coverage theater: calls add() but doesn't assert on its return.
    theater = (
        "from adder import add\n"
        "def test_calls():\n    add(1, 2)\n"
    )
    _seed_fixture(fixtures, "m", prompt_text, theater)

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    report = generate_tests_for_module(
        module_path, llm, prompts_dir=prompts_dir
    )
    assert report.kept is False
    assert "theater" in report.reason


@pytest.mark.parametrize(
    "mutation_name",
    ["flip_bool", "swap_addsub", "swap_eq_neq", "perturb_int"],
)
def test_every_mutation_advertised(mutation_name: str):
    """Regression guard: don't drop mutations silently."""
    from pipeline.hygiene.bug_injector import _MUTATIONS
    names = [name for name, _ in _MUTATIONS]
    assert mutation_name in names
