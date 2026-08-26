"""
Generate unit tests for low-coverage modules.

Two-step process:

1. Ask the LLM (via :class:`LLMClient`) to draft pytest tests for the
   target module.
2. Filter with mutation testing (:mod:`bug_injector`). A test that keeps
   passing while the module's function is trivially mutated isn't
   testing behavior; we drop it.

The filter is per test-file, per target function. If a mutant kills at
least one assertion in the file, we keep the file. If every mutant on
every target function still passes, we throw the file away.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..common.llm_client import LLMClient
from ..common.prompts.loader import load_prompt
from .bug_injector import (
    apply_mutations_to_function,
    run_test_against_source,
)

_DEFAULT_TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent / "common" / "prompts"
)


@dataclass
class GeneratedTestReport:
    module_path: Path
    kept: bool
    test_source: str
    reason: str = ""
    mutants_killed: list[str] = field(default_factory=list)


def generate_tests_for_module(
    module_path: Path,
    llm: LLMClient,
    *,
    prompts_dir: Path | None = None,
    max_target_functions: int = 5,
) -> GeneratedTestReport:
    module_source = module_path.read_text()
    tpl = load_prompt(
        "generate_tests",
        prompts_dir=prompts_dir or _DEFAULT_TEMPLATE_DIR,
    )
    prompt = tpl.render(
        module_path=module_path.as_posix(),
        module_source=module_source,
    )
    response = llm.complete(prompt, purpose="generate_tests")
    test_source = _strip_code_fences(response.text).strip() + "\n"

    module_stem = module_path.stem
    passes_baseline, out = run_test_against_source(
        module_stem, module_source, test_source
    )
    if not passes_baseline:
        return GeneratedTestReport(
            module_path=module_path,
            kept=False,
            test_source=test_source,
            reason=f"baseline test run failed: {out[-500:]}",
        )

    targets = _target_function_names(test_source, module_source)[
        :max_target_functions
    ]
    if not targets:
        return GeneratedTestReport(
            module_path=module_path,
            kept=False,
            test_source=test_source,
            reason="no target functions detectable from test source",
        )

    killed: list[str] = []
    for fn_name in targets:
        for mutant in apply_mutations_to_function(module_source, fn_name):
            still_passes, _ = run_test_against_source(
                module_stem, mutant.source, test_source
            )
            if not still_passes:
                killed.append(f"{fn_name}:{mutant.name}")

    if not killed:
        return GeneratedTestReport(
            module_path=module_path,
            kept=False,
            test_source=test_source,
            reason=(
                "coverage theater: no mutation killed by tests "
                f"(targets tried: {targets})"
            ),
        )

    return GeneratedTestReport(
        module_path=module_path,
        kept=True,
        test_source=test_source,
        mutants_killed=killed,
    )


def _target_function_names(test_source: str, module_source: str) -> list[str]:
    """Names defined in the module that the test source references."""
    try:
        mod_defs = {
            node.name
            for node in ast.walk(ast.parse(module_source))
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
    except SyntaxError:
        return []
    try:
        called: set[str] = set()
        for node in ast.walk(ast.parse(test_source)):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
    except SyntaxError:
        return []
    return sorted(called & mod_defs)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return text
    body = stripped[first_newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3].rstrip() + "\n"
    return body
