"""
Import edge extraction.

Produces one :class:`Edge` per distinct (source_module, target_module)
pair. ``from x import y`` targets module ``x`` (not the imported name),
because import-graph reasoning is about which modules depend on which
modules, not about which specific symbols are borrowed.

Relative imports are resolved against the source module's dotted id.
Packages (``__init__.py``) and regular modules follow slightly
different level semantics — see :func:`_resolve_from_import`.

Targets that don't resolve to any known module go to a synthetic node
under :data:`EXTERNAL_PREFIX`. Downstream code can filter or ignore
those depending on the analysis.
"""

from __future__ import annotations

import ast

from ..schema import Edge
from ..walkers.python import ParsedModule

EXTERNAL_PREFIX = "<external>"


def extract_import_edges(
    module: ParsedModule,
    *,
    known_module_ids: set[str] | None = None,
) -> list[Edge]:
    known = known_module_ids or set()
    is_pkg_init = module.path.name == "__init__.py"

    raw: list[tuple[str, str, dict]] = []

    for stmt in ast.walk(module.tree):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                target = _resolve_target(alias.name, known)
                raw.append(
                    (module.module_id, target, {"kind": "absolute"})
                )
        elif isinstance(stmt, ast.ImportFrom):
            resolved_prefix = _resolve_from_import(
                stmt, module.module_id, is_pkg_init
            )
            if stmt.module:
                # from x import y, z — target is module x
                target = _resolve_target(resolved_prefix, known)
                raw.append(
                    (
                        module.module_id,
                        target,
                        {
                            "kind": "from",
                            "names": [a.name for a in stmt.names],
                        },
                    )
                )
            else:
                # from . import a, b — each name is a submodule of resolved_prefix
                for alias in stmt.names:
                    submodule_id = (
                        f"{resolved_prefix}.{alias.name}"
                        if resolved_prefix
                        else alias.name
                    )
                    target = _resolve_target(submodule_id, known)
                    raw.append(
                        (
                            module.module_id,
                            target,
                            {"kind": "from_submodule"},
                        )
                    )

    return _dedupe(raw)


def _resolve_target(name: str, known: set[str]) -> str:
    if name in known:
        return name
    # Longest-prefix match: import glom.core when known has glom
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known:
            return name
        parts.pop()
    return f"{EXTERNAL_PREFIX}.{name}"


def _resolve_from_import(
    stmt: ast.ImportFrom,
    source_module_id: str,
    is_package_init: bool,
) -> str:
    module_name = stmt.module or ""
    level = stmt.level or 0

    if level == 0:
        return module_name

    parts = source_module_id.split(".")
    # For a package's __init__ module: level 1 refers to the package
    # itself, level 2 to its parent, etc. For a submodule: level 1
    # refers to the containing package (one step up).
    strip = level - 1 if is_package_init else level
    if strip > len(parts):
        return module_name  # over-relative; return the fragment as-is
    parent_parts = parts[: len(parts) - strip]
    if module_name:
        return ".".join(parent_parts + module_name.split("."))
    return ".".join(parent_parts) if parent_parts else module_name


def _dedupe(raw: list[tuple[str, str, dict]]) -> list[Edge]:
    seen: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for source, target, meta in raw:
        key = (source, target)
        if key not in seen:
            seen[key] = dict(meta)
            order.append(key)
            continue
        # merge from-names if any
        existing = seen[key]
        new_names = meta.get("names") or []
        if new_names:
            existing_names = existing.setdefault("names", [])
            for n in new_names:
                if n not in existing_names:
                    existing_names.append(n)

    return [
        Edge(source=s, target=t, type="imports", metadata=seen[(s, t)])
        for s, t in order
    ]
