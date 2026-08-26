"""
Node extraction from a parsed Python module.

Produces one :class:`Node` per module, class, function, and method.
Node ids are stable dotted paths that mirror Python's import system:

- module ``glom.core`` → ``id="glom.core"``, ``type="module"``
- class ``Spec`` in ``glom.core`` → ``id="glom.core.Spec"``, ``type="class"``
- function ``glom`` in ``glom.core`` → ``id="glom.core.glom"``, ``type="function"``
- method ``match`` in ``Spec`` → ``id="glom.core.Spec.match"``, ``type="method"``

Nested functions (a function defined inside another function) are not
extracted — they rarely have observable behavior in isolation and
would explode the id space without adding value for downstream mining.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..schema import Node
from ..walkers.python import ParsedModule


def extract_nodes(module: ParsedModule, *, repo_root: Path) -> list[Node]:
    nodes: list[Node] = [_module_node(module, repo_root)]
    for def_node, path_stack, is_method in _walk_top_level_defs(
        module.tree, [module.module_id]
    ):
        nodes.append(
            _def_to_node(def_node, path_stack, is_method, module.path, repo_root)
        )
    return nodes


def _module_node(module: ParsedModule, repo_root: Path) -> Node:
    return Node(
        id=module.module_id,
        type="module",
        file=_rel(module.path, repo_root),
        line=1,
        end_line=_module_end_line(module.tree),
        docstring=ast.get_docstring(module.tree),
        signature=None,
        is_public=_is_public(module.module_id.rsplit(".", 1)[-1]),
    )


def _def_to_node(
    def_node: ast.AST,
    path_stack: list[str],
    is_method: bool,
    path: Path,
    repo_root: Path,
) -> Node:
    node_id = ".".join(path_stack)
    if isinstance(def_node, ast.ClassDef):
        node_type = "class"
        signature = None
    elif isinstance(def_node, ast.FunctionDef | ast.AsyncFunctionDef):
        node_type = "method" if is_method else "function"
        signature = "(" + ast.unparse(def_node.args) + ")"
    else:  # pragma: no cover — walker filters to these types
        raise TypeError(f"unexpected def type: {type(def_node)!r}")

    return Node(
        id=node_id,
        type=node_type,
        file=_rel(path, repo_root),
        line=def_node.lineno,  # type: ignore[attr-defined]
        end_line=getattr(def_node, "end_lineno", def_node.lineno),  # type: ignore[attr-defined]
        docstring=ast.get_docstring(def_node),
        signature=signature,
        is_public=_is_public(def_node.name),  # type: ignore[attr-defined]
    )


def _walk_top_level_defs(node: ast.AST, path: list[str]):
    """Yield ``(ast_node, path_stack, is_method)`` for defs.

    Recurses into class bodies (so methods are yielded as inside_class=True)
    but not into function bodies.
    """
    for child in getattr(node, "body", []):
        if isinstance(child, ast.ClassDef):
            new_path = path + [child.name]
            yield child, new_path, False
            yield from _walk_class_body(child, new_path)
        elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            new_path = path + [child.name]
            yield child, new_path, _inside_class(path)


def _walk_class_body(cls: ast.ClassDef, path: list[str]):
    for child in cls.body:
        if isinstance(child, ast.ClassDef):
            new_path = path + [child.name]
            yield child, new_path, False
            yield from _walk_class_body(child, new_path)
        elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            new_path = path + [child.name]
            yield child, new_path, True


def _inside_class(path: list[str]) -> bool:
    # Called only at module-top-level in _walk_top_level_defs, so always False.
    # Kept explicit to match the class-body helper contract.
    return False


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _module_end_line(tree: ast.Module) -> int:
    end = 0
    for node in ast.walk(tree):
        line = getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)
        if line and line > end:
            end = line
    return end


def _is_public(name: str) -> bool:
    return bool(name) and not name.startswith("_")
