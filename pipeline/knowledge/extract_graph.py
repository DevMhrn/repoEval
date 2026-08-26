"""
Static graph extraction.

Walks the repo's AST (Python-first via `ast`; tree-sitter later for polyglot).
Produces nodes for:
    - files, packages
    - classes, functions, methods
and edges for:
    - imports (module -> module)
    - calls   (function -> function, best-effort by name resolution)
    - defines (file -> {class, function})

Every node carries a stable id: dotted.path.name — same convention as
Python's import system, so a task instruction can reference a node
unambiguously.

Phase 0 status: STUB.
"""

from __future__ import annotations

from pathlib import Path


def extract_graph(repo_path: Path) -> dict:
    raise NotImplementedError("Phase 2")
