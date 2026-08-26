"""
Call edge extraction.

For every function or method defined in a :class:`ParsedModule`, walk
its body for ``Call`` expressions and emit :class:`Edge` records to any
callee that resolves against ``known_node_ids``. Resolution is by
NAME, using a per-module map built from imports and top-level defs.

Explicitly out of scope
-----------------------
- Dynamic dispatch (``getattr``, ``globals()[...]``, string exec)
- Method resolution through ``self.foo()`` — we do our best via
  attribute chains, but MRO awareness is not attempted
- Higher-order calls (``foo()()``)

The graph docs call this out. Downstream consumers that need call
graphs precise enough to do slicing should reach for a real static
analyzer; the shape we build here is good enough for candidate
mining, coverage joining, and diversity heuristics.
"""

from __future__ import annotations

import ast

from ..schema import Edge
from ..walkers.python import ParsedModule


def extract_call_edges(
    module: ParsedModule,
    *,
    known_node_ids: set[str],
) -> list[Edge]:
    name_map = _build_name_map(module)
    aggregated: dict[tuple[str, str], Edge] = {}

    for containing_id, fn_node in _iter_function_defs(
        module.tree, [module.module_id]
    ):
        for call in _iter_calls(fn_node):
            callee_id = _resolve_call(call, name_map, known_node_ids)
            if callee_id is None or callee_id == containing_id:
                continue
            key = (containing_id, callee_id)
            if key in aggregated:
                aggregated[key].weight += 1.0
            else:
                aggregated[key] = Edge(
                    source=containing_id,
                    target=callee_id,
                    type="calls",
                )

    return sorted(aggregated.values(), key=lambda e: (e.source, e.target))


def _iter_function_defs(node: ast.AST, path: list[str]):
    for child in getattr(node, "body", []):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            containing_id = ".".join(path + [child.name])
            yield containing_id, child
        elif isinstance(child, ast.ClassDef):
            new_path = path + [child.name]
            yield from _iter_function_defs(child, new_path)


def _iter_calls(fn_node: ast.AST):
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            yield node


def _build_name_map(module: ParsedModule) -> dict[str, str]:
    """Map local name → best-effort target node id."""
    name_map: dict[str, str] = {}

    for child in module.tree.body:
        if isinstance(
            child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ):
            name_map[child.name] = f"{module.module_id}.{child.name}"

    is_pkg_init = module.path.name == "__init__.py"
    for stmt in ast.walk(module.tree):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    # ``import x.y as z``  → ``z`` refers to ``x.y``
                    name_map[alias.asname] = alias.name
                else:
                    # ``import x.y.z``    → ``x`` (top-level) refers to ``x``
                    top = alias.name.split(".")[0]
                    name_map[top] = top
        elif isinstance(stmt, ast.ImportFrom):
            prefix = _from_import_prefix(stmt, module.module_id, is_pkg_init)
            for alias in stmt.names:
                local = alias.asname or alias.name
                target = (
                    f"{prefix}.{alias.name}" if prefix else alias.name
                )
                name_map[local] = target
    return name_map


def _from_import_prefix(
    stmt: ast.ImportFrom, source_module_id: str, is_pkg_init: bool
) -> str:
    module_name = stmt.module or ""
    level = stmt.level or 0
    if level == 0:
        return module_name
    parts = source_module_id.split(".")
    strip = level - 1 if is_pkg_init else level
    if strip > len(parts):
        return module_name
    parent = ".".join(parts[: len(parts) - strip])
    if module_name and parent:
        return f"{parent}.{module_name}"
    return parent or module_name


def _resolve_call(
    call: ast.Call,
    name_map: dict[str, str],
    known: set[str],
) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        target = name_map.get(func.id)
        if target and target in known:
            return target
        return None
    if isinstance(func, ast.Attribute):
        chain = _attribute_chain(func)
        if not chain:
            return None
        head, *rest = chain
        base = name_map.get(head, head)
        candidate = ".".join([base, *rest])
        if candidate in known:
            return candidate
    return None


def _attribute_chain(node: ast.Attribute) -> list[str] | None:
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.insert(0, cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.insert(0, cur.id)
        return parts
    return None
