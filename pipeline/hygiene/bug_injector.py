"""
Mutation-based anti-theater guard.

Given a Python source file and a candidate test file, we mutate one
function at a time and re-run the test. Any test that keeps passing
under a mutation isn't actually testing observable behavior — it's
coverage theater — and gets discarded.

The mutations are small, AST-level, and deliberately obvious:

- flip a boolean literal (``True`` ↔ ``False``)
- swap ``+`` and ``-`` in a binary op
- swap ``==`` and ``!=`` in a comparison
- perturb an integer constant by ``+1``

Each mutation applies at most once per pass — enough signal to reveal
theater without exploding the mutant space. If none of the mutations
touch the target function (e.g., the function is a no-op) we don't
have a way to test the test, so the caller gets an empty list and can
decide the policy.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutant:
    name: str
    source: str


def apply_mutations_to_function(
    module_source: str, target_fn: str
) -> list[Mutant]:
    """Return up to one mutant per mutation kind."""
    if not _module_defines(module_source, target_fn):
        return []

    mutants: list[Mutant] = []
    for name, transformer_cls in _MUTATIONS:
        candidate = _apply_one(module_source, target_fn, transformer_cls)
        if candidate is not None:
            mutants.append(Mutant(name=name, source=candidate))
    return mutants


def run_test_against_source(
    module_name: str,
    module_source: str,
    test_source: str,
    *,
    timeout_sec: int = 30,
) -> tuple[bool, str]:
    """Write both files to a temp dir, run pytest, return ``(passed, output)``."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / f"{module_name}.py").write_text(module_source)
        (tmp_path / f"test_{module_name}.py").write_text(test_source)
        try:
            result = subprocess.run(
                ["pytest", "-q", "--no-header", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout"
        return result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def _module_defines(source: str, target_fn: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == target_fn:
            return True
    return False


def _apply_one(
    source: str, target_fn: str, transformer_cls: type[_Transformer]
) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != target_fn:
            continue
        transformer = transformer_cls()
        transformer.visit(node)
        if transformer.applied:
            return ast.unparse(tree)
        return None
    return None


class _Transformer(ast.NodeTransformer):
    """Base for a one-shot AST mutation."""

    applied: bool = False


class _FlipBool(_Transformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self.applied:
            return node
        if isinstance(node.value, bool):
            self.applied = True
            return ast.copy_location(ast.Constant(not node.value), node)
        return node


class _SwapAddSub(_Transformer):
    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if isinstance(node.op, ast.Add):
            node.op = ast.Sub()
            self.applied = True
        elif isinstance(node.op, ast.Sub):
            node.op = ast.Add()
            self.applied = True
        return node


class _SwapEqNeq(_Transformer):
    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        new_ops: list[ast.cmpop] = []
        for op in node.ops:
            if not self.applied and isinstance(op, ast.Eq):
                new_ops.append(ast.NotEq())
                self.applied = True
            elif not self.applied and isinstance(op, ast.NotEq):
                new_ops.append(ast.Eq())
                self.applied = True
            else:
                new_ops.append(op)
        node.ops = new_ops
        return node


class _PerturbInt(_Transformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self.applied:
            return node
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            self.applied = True
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node


_MUTATIONS: list[tuple[str, type[_Transformer]]] = [
    ("flip_bool", _FlipBool),
    ("swap_addsub", _SwapAddSub),
    ("swap_eq_neq", _SwapEqNeq),
    ("perturb_int", _PerturbInt),
]
